import json
import os
import threading
import time
import unittest
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from cli_retrac_mcts.agent import TaskRunner
from cli_retrac_mcts.mcts import MCTSConfig
from cli_retrac_mcts.models import ModelCallError, StructuredContext, TaskSpec
from cli_retrac_mcts.retrac_adapter import (
    OpenAICompatibleJSONClient,
    RetracModelConfig,
    RetracPolicyAdapter,
    _request_bytes_with_hard_timeout,
    _safe_error_text,
    _truncate,
)
from cli_retrac_mcts.rules import TaskRuleStore
from examples.demo_counter import CounterEnvironment


@dataclass
class ScriptedClient:
    responses: list[dict]
    prompts: list[str] = field(default_factory=list)
    reasoning_efforts: list[str | None] = field(default_factory=list)
    prompt_cache_keys: list[str | None] = field(default_factory=list)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        reasoning_effort: str | None = None,
        prompt_cache_key: str | None = None,
    ) -> dict:
        self.prompts.append(user_prompt)
        self.reasoning_efforts.append(reasoning_effort)
        self.prompt_cache_keys.append(prompt_cache_key)
        if not self.responses:
            raise AssertionError("unexpected model call")
        return self.responses.pop(0)


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body


class EmptyHTTPResponse(FakeHTTPResponse):
    def __init__(self) -> None:
        self._body = b""


class SlowHTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        time.sleep(3)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args) -> None:
        pass


class StreamingKeepAliveHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for _ in range(3):
            self.wfile.write(b": keep-alive\n\n")
            self.wfile.flush()
            time.sleep(0.4)
        self.wfile.write(
            b'data: {"choices":[{"delta":{"content":"{\\"ok\\":"}}]}\n\n'
        )
        self.wfile.write(
            b'data: {"choices":[{"delta":{"content":"true}"}}]}\n\n'
        )
        self.wfile.write(
            b'data: {"choices":[],"usage":{"prompt_tokens":100,'
            b'"completion_tokens":5,"total_tokens":105,'
            b'"prompt_tokens_details":{"cached_tokens":64}}}\n\n'
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args) -> None:
        pass


def model_config(**overrides) -> RetracModelConfig:
    values = {
        "model_name": "test-model",
        "base_url": "http://model.test/v1",
        "api_key": "secret",
        "request_attempts": 1,
        "parse_attempts": 2,
        "retry_interval_seconds": 0.0,
        #普通HTTP客户端测试需要在当前进程中保留mock；生产默认仍启用子进程硬超时
        "hard_timeout_process": False,
    }
    values.update(overrides)
    return RetracModelConfig(**values)


class RetracAdapterTests(unittest.TestCase):
    def test_observation_truncation_keeps_middle_diagnostics(self) -> None:
        content = "HEAD\n" + ("ordinary output\n" * 300)
        content += "Traceback: important middle failure\n"
        content += ("more ordinary output\n" * 300) + "TAIL"

        shortened = _truncate(content, 1_200)

        self.assertLessEqual(len(shortened), 1_200)
        self.assertIn("HEAD", shortened)
        self.assertIn("important middle failure", shortened)
        self.assertIn("TAIL", shortened)

    def test_solve_mode_prompt_requires_modification_and_verification(self) -> None:
        client = ScriptedClient(
            [{
                "actions": [{
                    "name": "edit_and_test",
                    "rationale": "implement the solution",
                    "semantic_direction_id": "implement_solution",
                    "semantic_direction_label": "Implement solution",
                    "expected_effect": "write the fix and run tests",
                    "applied_rule_ids": [],
                    "intent": "candidate",
                    "commands": [{
                        "argv": ["python", "-c", "print('edit')"],
                        "description": "edit and test",
                    }],
                    "verification_commands": [{
                        "argv": ["python", "-m", "pytest"],
                        "description": "independently run the test suite",
                    }],
                }],
            }]
        )
        adapter = RetracPolicyAdapter(model_config(), client=client)

        adapter.propose_actions(
            task=TaskSpec("task-a", "repair failing tests"),
            context=StructuredContext(task_goal="repair failing tests"),
            rules=(),
            limit=1,
            solve_mode=True,
            budget_status={
                "remaining_iterations": 2,
                "remaining_action_tool_calls": 4,
                "reserved_final_verification_tool_calls": 8,
                "maximum_commands_for_next_action": 2,
                "urgency": "closing",
            },
        )

        self.assertIn("The search is now in solve mode", client.prompts[0])
        self.assertIn("A candidate must directly modify", client.prompts[0])
        self.assertIn("do not fall back to broad directory scans", client.prompts[0])
        self.assertIn("verification_commands", client.prompts[0])
        self.assertIn("negative or adversarial case", client.prompts[0])
        self.assertIn("Current runtime budget status", client.prompts[0])
        self.assertIn('"remaining_iterations":2', client.prompts[0])
        self.assertIn("The run is closing", client.prompts[0])
        self.assertIn("Maximum commands per macro action: 2", client.prompts[0])
        self.assertEqual(client.reasoning_efforts, ["max"])
        self.assertEqual(client.prompt_cache_keys, ["retrac-v2-solve-actions"])
        self.assertLess(
            client.prompts[0].index("Return this schema"),
            client.prompts[0].index("Task specification"),
        )

    def test_action_parser_enforces_current_runtime_command_budget(self) -> None:
        adapter = RetracPolicyAdapter(model_config(), client=ScriptedClient([]))
        payload = {
            "actions": [{
                "name": "too_large",
                "rationale": "would consume the verification reserve",
                "semantic_direction_id": "repair",
                "semantic_direction_label": "Repair",
                "intent": "candidate",
                "commands": [{
                    "argv": ["python", "-c", "print('edit')"],
                    "description": "edit",
                }],
                "verification_commands": [{
                    "argv": ["python", "-m", "pytest"],
                    "description": "verify",
                }],
            }],
        }

        with self.assertRaisesRegex(ValueError, "current runtime budget"):
            adapter._parse_actions(
                payload,
                limit=1,
                solve_mode=True,
                max_total_commands=1,
            )

    def test_action_model_selects_only_from_retrieved_rule_candidates(self) -> None:
        store = TaskRuleStore(task_id="task-a")
        rule = store.add(
            task_id="task-a",
            kind="recommend",
            semantic_direction_id="inspect_tests",
            action_name="read_tests",
            evidence="test inspection worked",
            condition="tests are failing",
            guidance="inspect the failing tests",
        )
        client = ScriptedClient(
            [
                {
                    "actions": [
                        {
                            "name": "analyze_test_failure",
                            "rationale": "apply the retrieved testing rule",
                            "semantic_direction_id": "analyze_tests",
                            "semantic_direction_label": "Analyze test failures",
                            "expected_effect": "identify the failing assertion",
                            "applied_rule_ids": [rule.rule_id],
                            "commands": [
                                {
                                    "argv": ["python", "-m", "unittest"],
                                    "description": "run tests",
                                }
                            ],
                        }
                    ]
                }
            ]
        )
        adapter = RetracPolicyAdapter(model_config(), client=client)

        actions = adapter.propose_actions(
            task=TaskSpec("task-a", "repair failing tests"),
            context=StructuredContext(task_goal="repair failing tests"),
            rules=(rule,),
            limit=1,
        )

        self.assertEqual(actions[0].applied_rule_ids, (rule.rule_id,))
        self.assertIn("Top-k candidate rules", client.prompts[0])
        self.assertIn("Experience-guided priority", client.prompts[0])

    def test_avoid_experience_guides_a_distinct_exploration_action(self) -> None:
        store = TaskRuleStore(task_id="task-a")
        rule = store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="repair_parser",
            action_name="repeat_failed_patch",
            evidence="the previous patch caused a regression",
            guidance="use the failing assertion to construct a different patch",
        )
        client = ScriptedClient(
            [{
                "actions": [{
                    "name": "inspect_failing_assertion",
                    "rationale": "avoid repeating the failed patch",
                    "semantic_direction_id": "repair_parser",
                    "semantic_direction_label": "Repair parser",
                    "expected_effect": "identify a different repair",
                    "applied_rule_ids": [rule.rule_id],
                    "intent": "explore",
                    "commands": [{
                        "argv": ["python", "-m", "pytest"],
                        "description": "inspect the focused failure",
                    }],
                    "verification_commands": [],
                }],
            }]
        )
        adapter = RetracPolicyAdapter(model_config(), client=client)

        adapter.propose_actions(
            task=TaskSpec("task-a", "repair parser"),
            context=StructuredContext(task_goal="repair parser"),
            rules=(rule,),
            limit=1,
        )

        self.assertIn("Experience-guided exploration", client.prompts[0])
        self.assertIn("base action capacity", client.prompts[0])
        self.assertIn("Node visit count never changes this capacity", client.prompts[0])
        self.assertIn("instead of repeating", client.prompts[0])

    def test_action_parser_rejects_rule_ids_outside_candidates(self) -> None:
        adapter = RetracPolicyAdapter(model_config(), client=ScriptedClient([]))
        payload = {
            "actions": [
                {
                    "name": "inspect",
                    "rationale": "test",
                    "semantic_direction_id": "inspect",
                    "semantic_direction_label": "Inspect",
                    "applied_rule_ids": ["unknown-rule"],
                    "commands": [
                        {"argv": ["python", "-V"], "description": "check python"}
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "outside the retrieved candidates"):
            adapter._parse_actions(
                payload,
                limit=1,
                allowed_rule_ids=frozenset({"known-rule"}),
            )

    def test_windows_read_only_builtin_is_wrapped_by_cmd(self) -> None:
        adapter = RetracPolicyAdapter(model_config(), client=ScriptedClient([]))
        raw_commands = [
            {
                "argv": ["type", "tests\\test_pricing.py"],
                "description": "read tests",
            }
        ]
        with patch("cli_retrac_mcts.retrac_adapter.platform.system", return_value="Windows"):
            commands = adapter._parse_commands(raw_commands)

        self.assertEqual(commands[0].argv[:4], ("cmd.exe", "/d", "/s", "/c"))
        self.assertIn("type", commands[0].argv[4])
        self.assertIn("tests\\test_pricing.py", commands[0].argv[4])

    def test_windows_builtin_rejects_shell_metacharacters(self) -> None:
        adapter = RetracPolicyAdapter(model_config(), client=ScriptedClient([]))
        raw_commands = [
            {
                "argv": ["type", "README.md", "&", "del", "important.txt"],
                "description": "unsafe command",
            }
        ]
        with patch("cli_retrac_mcts.retrac_adapter.platform.system", return_value="Windows"):
            with self.assertRaisesRegex(ValueError, "unsafe characters"):
                adapter._parse_commands(raw_commands)

    def test_deepseek_provider_uses_independent_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "deepseek-secret\r\n"},
            clear=True,
        ):
            config = RetracModelConfig.from_environment(provider="deepseek")

        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.model_name, "deepseek-v4-flash")
        self.assertEqual(config.api_key, "deepseek-secret")

    def test_api_error_text_redacts_bearer_token(self) -> None:
        secret = "sk-this-token-must-not-appear"
        message = _safe_error_text(
            ValueError(f"Invalid header value b'Bearer {secret}\\r'")
        )

        self.assertNotIn(secret, message)
        self.assertIn("[REDACTED]", message)

    def test_openai_provider_keeps_original_environment_variables(self) -> None:
        environment = {
            "OPENAI_API_KEY": "openai-secret",
            "OPENAI_API_BASE": "https://api.openai.test/v1",
            "OPENAI_MODEL": "openai-test-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = RetracModelConfig.from_environment(provider="openai")

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.base_url, environment["OPENAI_API_BASE"])
        self.assertEqual(config.model_name, environment["OPENAI_MODEL"])
        self.assertEqual(config.api_key, environment["OPENAI_API_KEY"])

    def test_adapter_drives_one_complete_mcts_transition(self) -> None:
        client = ScriptedClient(
            [
                {
                    "semantic_directions": [
                        {
                            "direction_id": "reach_target",
                            "label": "到达目标值",
                            "status": "unexplored",
                            "evidence": [],
                        },
                        {
                            "direction_id": "verify_target",
                            "label": "验证目标状态",
                            "status": "unexplored",
                            "evidence": [],
                        },
                    ],
                    "bootstrap_action": {
                            "name": "直接到达目标",
                            "rationale": "验证目标状态",
                            "semantic_direction_id": "reach_target",
                            "semantic_direction_label": "到达目标值",
                            "expected_effect": "计数器等于3",
                            "intent": "candidate",
                            "commands": [
                                {
                                    "argv": ["counter", "add", "3"],
                                    "description": "将计数器增加3",
                                    "cwd": ".",
                                    "timeout_seconds": 60,
                                    "stdin": None,
                                }
                            ],
                            "verification_commands": [
                                {
                                    "argv": ["counter", "verify", "3"],
                                    "description": "独立确认计数器等于3",
                                    "cwd": ".",
                                    "timeout_seconds": 60,
                                    "stdin": None,
                                }
                            ],
                        }
                },
                {
                    "assessment": {
                        "direction_status": "covered",
                        "task_success": True,
                        "satisfied_success_criteria": ["counter equals 3"],
                        "feedback": "命令输出为3，成功标准已满足。",
                    },
                    "next_context": {
                        "task_goal": "Reach counter value 3.",
                        "current_solution": "counter=3",
                        "facts_and_evidence": [
                            {
                                "claim": "counter equals 3",
                                "source": "counter add 3",
                                "verified": "yes",
                            }
                        ],
                        "analysis_and_conclusions": ["目标已达到"],
                        "unresolved_issues": [],
                        "incomplete_plans": [],
                        "semantic_directions": [
                            {
                                "direction_id": "reach_target",
                                "label": "到达目标值",
                                "status": "covered",
                                "evidence": ["counter=3"],
                            }
                        ],
                        "environment_summary": "value=3",
                    },
                },
            ]
        )
        adapter = RetracPolicyAdapter(model_config(), client=client)
        task = TaskSpec.create("Reach counter value 3.", ("counter equals 3",))
        with self.assertLogs("cli_retrac_mcts.mcts", level="INFO") as progress:
            result = TaskRunner(
                CounterEnvironment(),
                adapter,
                MCTSConfig(
                    max_iterations=2,
                    initial_branching_factor=2,
                    post_success_iterations=0,
                ),
            ).run(task)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.stop_reason, "verified_success")
        self.assertTrue(result.transitions[-1].assessment.verified_success)
        self.assertEqual(result.best_node.context.current_solution, "counter=3")
        self.assertEqual(
            {
                item.direction_id
                for item in result.transitions[0].state_before.semantic_directions
            },
            {"reach_target", "verify_target"},
        )
        self.assertEqual(result.transitions[0].semantic_coverage_after, 0.5)
        #初始动作生成一次、转移评估与压缩合并一次，共两次模型请求
        self.assertEqual(len(client.prompts), 2)
        self.assertEqual(
            client.prompt_cache_keys,
            ["retrac-v2-initial-plan", "retrac-v2-transition-update"],
        )
        self.assertLess(
            client.prompts[0].index("Return this schema"),
            client.prompts[0].index("Task specification"),
        )
        self.assertLess(
            client.prompts[1].index("Return this schema"),
            client.prompts[1].index("Task specification"),
        )
        self.assertIn(
            "Return the assessment and next_context together",
            client.prompts[1],
        )
        messages = "\n".join(progress.output)
        self.assertIn("迭代 1/2", messages)
        self.assertIn("语义覆盖率", messages)
        self.assertIn("搜索结束", messages)

    def test_invalid_assessment_is_repaired_once(self) -> None:
        client = ScriptedClient(
            [
                {"direction_status": "done", "task_success": "false", "feedback": "bad"},
                {"direction_status": "exploring", "task_success": False, "feedback": "partial"},
            ]
        )
        adapter = RetracPolicyAdapter(model_config(), client=client)
        with self.assertLogs("cli_retrac_mcts.retrac_adapter", level="INFO") as progress:
            assessment = adapter._ask_and_parse("test", adapter._parse_assessment)

        self.assertEqual(assessment.direction_status, "exploring")
        self.assertFalse(assessment.task_success)
        self.assertIn("previous output failed schema validation", client.prompts[1])
        messages = "\n".join(progress.output)
        self.assertIn("格式尝试 1/2", messages)
        self.assertIn("输出格式不合格", messages)
        self.assertIn("输出已通过结构校验", messages)

    def test_assessment_cannot_set_runtime_verified_success(self) -> None:
        with self.assertRaisesRegex(ValueError, "runtime-only"):
            RetracPolicyAdapter._parse_assessment(
                {
                    "direction_status": "covered",
                    "task_success": True,
                    "satisfied_success_criteria": ["done"],
                    "verified_success": True,
                    "feedback": "claimed",
                },
                allowed_success_criteria=("done",),
            )

    def test_task_success_requires_exact_criterion_coverage(self) -> None:
        with self.assertRaisesRegex(ValueError, "every task success criterion"):
            RetracPolicyAdapter._parse_assessment(
                {
                    "direction_status": "covered",
                    "task_success": True,
                    "satisfied_success_criteria": ["criterion a"],
                    "feedback": "partial",
                },
                allowed_success_criteria=("criterion a", "criterion b"),
            )
    def test_openai_compatible_client_builds_chat_completion_request(self) -> None:
        response = FakeHTTPResponse({
            "choices": [{"message": {"content": "```json\n{\"ok\": true}\n```"}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 5,
                "total_tokens": 105,
                "prompt_tokens_details": {
                    "cached_tokens": 64,
                    "cache_write_tokens": 32,
                },
            },
        })
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return response

        client = OpenAICompatibleJSONClient(model_config(timeout_seconds=42))
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            payload = client.complete_json(
                system_prompt="system",
                user_prompt="user",
                prompt_cache_key="retrac-v2-test",
            )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(captured["request"].full_url, "http://model.test/v1/chat/completions")
        self.assertEqual(captured["timeout"], 42)
        request_payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(request_payload["model"], "test-model")
        self.assertEqual(request_payload["response_format"], {"type": "json_object"})
        self.assertTrue(request_payload["stream"])
        self.assertEqual(request_payload["stream_options"], {"include_usage": True})
        self.assertEqual(request_payload["prompt_cache_key"], "retrac-v2-test")
        self.assertEqual(
            client.usage_summary(),
            {
                "model_calls": 1,
                "api_requests": 1,
                "api_responses": 1,
                "prompt_tokens": 100,
                "cached_prompt_tokens": 64,
                "cache_miss_prompt_tokens": 36,
                "cache_write_prompt_tokens": 32,
                "completion_tokens": 5,
                "cache_hit_rate": 0.64,
            },
        )

    def test_deepseek_request_explicitly_keeps_high_thinking_enabled(self) -> None:
        response = FakeHTTPResponse({
            "choices": [{"message": {"content": "{\"ok\": true}"}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 5,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
                "total_tokens": 105,
            },
        })
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            return response

        client = OpenAICompatibleJSONClient(model_config(provider="deepseek"))
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete_json(
                system_prompt="system",
                user_prompt="user",
                prompt_cache_key="must-not-be-forwarded",
            )

        request_payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(request_payload["thinking"], {"type": "enabled"})
        self.assertEqual(request_payload["reasoning_effort"], "high")
        self.assertNotIn("prompt_cache_key", request_payload)
        self.assertEqual(client.usage_summary()["cache_hit_rate"], 0.8)

    def test_production_client_routes_request_through_hard_timeout_process(self) -> None:
        raw = json.dumps(
            {"choices": [{"message": {"content": "{\"ok\": true}"}}]}
        ).encode("utf-8")
        client = OpenAICompatibleJSONClient(
            model_config(
                hard_timeout_process=True,
                timeout_seconds=17,
                max_wall_time_seconds=300,
            )
        )

        with patch(
            "cli_retrac_mcts.retrac_adapter._request_bytes_with_hard_timeout",
            return_value=raw,
        ) as request:
            payload = client.complete_json(system_prompt="system", user_prompt="user")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(request.call_args.kwargs["timeout_seconds"], 17)
        self.assertEqual(request.call_args.kwargs["max_wall_time_seconds"], 300)
        self.assertTrue(request.call_args.kwargs["stream_response"])

    def test_hard_timeout_terminates_a_slow_http_request(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHTTPHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(TimeoutError, "no activity"):
                _request_bytes_with_hard_timeout(
                    endpoint=f"http://127.0.0.1:{server.server_port}/chat/completions",
                    encoded=b"{}",
                    headers={"Content-Type": "application/json"},
                    timeout_seconds=1,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

        self.assertLess(time.monotonic() - started, 2.5)

    def test_stream_activity_extends_idle_timeout_without_exceeding_wall_limit(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), StreamingKeepAliveHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            raw = _request_bytes_with_hard_timeout(
                endpoint=f"http://127.0.0.1:{server.server_port}/chat/completions",
                encoded=b"{}",
                headers={"Content-Type": "application/json"},
                timeout_seconds=1,
                max_wall_time_seconds=4,
                stream_response=True,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["choices"][0]["message"]["content"], '{"ok":true}')
        self.assertEqual(payload["usage"]["prompt_tokens_details"]["cached_tokens"], 64)
        self.assertGreater(time.monotonic() - started, 1.0)

    def test_empty_http_body_has_an_explicit_diagnostic(self) -> None:
        client = OpenAICompatibleJSONClient(model_config(request_attempts=1))

        with patch("urllib.request.urlopen", return_value=EmptyHTTPResponse()):
            with self.assertRaisesRegex(ModelCallError, "HTTP response body is empty"):
                client.complete_json(system_prompt="system", user_prompt="user")

    def test_temporary_request_failures_use_capped_exponential_backoff(self) -> None:
        response = FakeHTTPResponse({"choices": [{"message": {"content": "{\"ok\": true}"}}]})
        client = OpenAICompatibleJSONClient(
            model_config(
                request_attempts=3,
                retry_interval_seconds=1.0,
                max_retry_interval_seconds=2.0,
            )
        )
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=[TimeoutError("first"), TimeoutError("second"), response],
            ) as urlopen,
            patch("cli_retrac_mcts.retrac_adapter.time.sleep") as sleep,
        ):
            payload = client.complete_json(system_prompt="system", user_prompt="user")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([item.args[0] for item in sleep.call_args_list], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
