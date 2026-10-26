"""Compare every recorded numerical metric; preserve missing-vs-disabled."""
from collections import Counter
from datetime import datetime,timezone,timedelta
import json
import statistics
from common import ROOT,save
from build_report import aggregate,usage

def metrics(summaries,grades):
    assert len(summaries)==len(grades) and all(g['grading_state']=='complete' for g in grades)
    aggregated=aggregate(summaries)
    f2p=[g['f2p']['step_score'] for g in grades]
    p2p=[g['p2p_step_score'] for g in grades]
    cases=[v for g in grades for v in g['p2p_cases'].values()]
    u=aggregated['usage'];n=len(summaries)
    all_keys=sorted({k for s in summaries for k,v in (s.get('mechanism_utilization') or {}).items()
        if isinstance(v,(int,float)) and not isinstance(v,bool)})
    aggregated.update(quality=dict(mean_f2p=statistics.mean(f2p),median_f2p=statistics.median(f2p),
        f2p_fully_passed=sum(g['f2p']['is_pass']==1 for g in grades),
        f2p_zero=sum(v==0 for v in f2p),f2p_positive=sum(v>0 for v in f2p),
        official_successes=sum(g['official_success'] for g in grades),
        p2p_fully_passed=sum(g['p2p_is_pass']==1 for g in grades),mean_p2p=statistics.mean(p2p),
        p2p_cases_passed=sum(cases),p2p_cases_total=len(cases)),
        interaction_rounds=sum(s['interaction_rounds'] for s in summaries),
        mean_tools=aggregated['tools']/n,mean_model_calls=u['model_calls']/n,
        mean_total_tokens=u['total_tokens']/n,
        median_elapsed_seconds=statistics.median(s['elapsed_seconds'] for s in summaries),
        cache_hit_fraction=u['cached_prompt_tokens']/u['prompt_tokens'] if u['prompt_tokens'] else None,
        per_role={role:{key:sum((s.get('model_usage') or {}).get(role,{}).get(key,0) or 0 for s in summaries)
            for key in u} for role in sorted({role for s in summaries for role in (s.get('model_usage') or {})})},
        all_mechanism_counts={key:sum((s.get('mechanism_utilization') or {}).get(key,0) or 0 for s in summaries) for key in all_keys})
    return aggregated

def main():
    data=json.loads((ROOT/'full-report/report-data.json').read_text())
    gen=data['original_generations'];grades=data['original_and_supplementary_grades']
    tasks=data['protocol']['tasks']
    raw_retry=data['network_retry_generation']
    def summary(method,task):return raw_retry if method=='raw' and task=='cs61_fa24_scheme' else gen[method+'--'+task]
    def grade(method,task):
        if method=='raw' and task=='cs61_fa24_scheme':return grades['roundtrip--cs61_fa24_scheme']
        if method=='dh' and task=='61810_pgtbl':return grades['roundtrip--outer-clock-fix--61810_pgtbl']
        return grades[method+'--'+task]
    result=dict(updated=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
        metrics20={m:metrics([summary(m,t['task']) for t in tasks],[grade(m,t['task']) for t in tasks]) for m in ('dh','raw')})
    graph_root=ROOT.parent/'longcli-planner-v3-10-20261004'
    graph_state=json.loads((graph_root/'paired-status.json').read_text())
    graph_summaries={s['task']:s for w in graph_state['workers'] for s in w['results']}
    graph_tasks=json.loads((graph_root/'protocol.json').read_text())['tasks']
    graph_names=[t['task'] for t in graph_tasks]
    assert graph_state['graded']==len(graph_names)==10
    graph_grades=[graph_state['results']['planner-v3--'+t] for t in graph_names]
    for name,g in zip(graph_names,graph_grades):
        assert g['artifact_sha256']==graph_summaries[name]['artifact']['sha256']
    result['same10']={m:metrics([summary(m,t) for t in graph_names],[grade(m,t) for t in graph_names]) for m in ('dh','raw')}
    result['same10']['graph']=metrics([graph_summaries[t] for t in graph_names],graph_grades)
    result['same10_tasks']=graph_names
    result['original_raw20_including_dns_failure']=aggregate([s for s in gen.values() if s['method']=='raw'])
    result['raw21_total_paid_generation_attempts']=aggregate([s for s in gen.values() if s['method']=='raw']+[raw_retry])
    result['generation_policy_notes']=['RAW effective20 uses authorized scheme retry; initial DNS failure retained separately.',
        'DH pgtbl evaluation outer clock 300->900; official internal limits, frozen source and model usage unchanged.',
        'RAW absent numerical mechanism fields are unmeasured/disabled, not evidence of zero failures.',
        'Elapsed sum is per-task durations summed, not campaign wall-clock.',
        'Token quantities are provider usage, not invoice cost.',
        'Graph has a distinct 10-task set; only same10 is a like-task comparison.']
    save(ROOT/'full-report/ALL-METRICS.json',result)
    labels=[('有效题数',lambda a:a['trials']),('平均F2P(%)',lambda a:100*a['quality']['mean_f2p']),
        ('中位F2P(%)',lambda a:100*a['quality']['median_f2p']),('F2P全过题数',lambda a:a['quality']['f2p_fully_passed']),
        ('F2P零分题数',lambda a:a['quality']['f2p_zero']),('整题完全通过',lambda a:a['quality']['official_successes']),
        ('P2P全过题数',lambda a:a['quality']['p2p_fully_passed']),('平均P2P(%)',lambda a:100*a['quality']['mean_p2p']),
        ('工具总数',lambda a:a['tools']),('每题平均工具',lambda a:a['mean_tools']),
        ('逻辑模型调用usage',lambda a:a['usage']['model_calls']),('runner interaction_rounds',lambda a:a['interaction_rounds']),
        ('wire/API请求',lambda a:a['usage']['api_requests']),('API回复',lambda a:a['usage']['api_responses']),
        ('输入tokens',lambda a:a['usage']['prompt_tokens']),('输出tokens',lambda a:a['usage']['completion_tokens']),
        ('总tokens',lambda a:a['usage']['total_tokens']),('每题平均tokens',lambda a:a['mean_total_tokens']),
        ('缓存命中输入tokens',lambda a:a['usage']['cached_prompt_tokens']),
        ('缓存命中占输入(%)',lambda a:100*a['cache_hit_fraction']),
        ('每题平均耗时分钟',lambda a:a['elapsed_seconds_mean']/60),
        ('每题中位耗时分钟',lambda a:a['median_elapsed_seconds']/60),
        ('题目耗时累计小时(非墙钟)',lambda a:a['elapsed_seconds_sum']/3600),
        ('自主提交题数',lambda a:a['submitted'])]
    def fmt(value):return f'{value:.4f}' if isinstance(value,float) else str(value)
    lines=['所有已记录指标对比',result['updated'],'RAW采用有效补跑；DH采用pgtbl补评。首次失败与评分时限变化均保留。','',
        '一、DH与RAW：同20题','指标\tDH\tRAW']
    for label,getter in labels:lines.append('\t'.join([label]+[fmt(getter(result['metrics20'][m])) for m in ('dh','raw')]))
    for method,a in result['metrics20'].items():
        lines += ['',method+' 退出原因：'+json.dumps(a['stop_reasons'],ensure_ascii=False),
                  method+' 传输/格式失败计数：'+json.dumps(a['failure_counts'],ensure_ascii=False),
                  method+' 按角色API计数：'+json.dumps(a['per_role'],ensure_ascii=False)]
    lines+=['','二、所有组件计数（—代表RAW未启用/未记录同名字段，不代表没有循环）','字段\tDH\tRAW']
    keys=sorted(set(result['metrics20']['dh']['all_mechanism_counts'])|set(result['metrics20']['raw']['all_mechanism_counts']))
    for key in keys:lines.append('\t'.join([key]+[str(result['metrics20'][m]['all_mechanism_counts'].get(key,'—')) for m in ('dh','raw')]))
    lines+=['','三、严格相同10题：DH、RAW、图搜索','指标\tDH\tRAW\t图搜索']
    for label,getter in labels:lines.append('\t'.join([label]+[fmt(getter(result['same10'][m])) for m in ('dh','raw','graph')]))
    lines+=['','图搜索退出原因：'+json.dumps(result['same10']['graph']['stop_reasons'],ensure_ascii=False),
            '图搜索所有组件计数：'+json.dumps(result['same10']['graph']['all_mechanism_counts'],ensure_ascii=False),
            '', '四、不可由已有日志可靠得出的指标',
            '真实人民币费用（无账单核对）；全局重复率/无效工具率（未统一独立标注）；记忆因果增益；统计显著性。',
            '曝光不是利用，自述不是证据，命令成功不是任务成功，正交放行不是获得新证据。',
            '逻辑请求usage与runner计数存在差异时分列，不强行合并；数值缺失不当作零。']
    (ROOT/'full-report/ALL-METRICS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('metrics20','same10')},ensure_ascii=False))

if __name__=='__main__':main()
