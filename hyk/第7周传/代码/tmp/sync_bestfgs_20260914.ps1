$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path -LiteralPath 'C:\Users\54177\Documents\ChatGPT\mcts\BestFGS_work').Path
$targetRoot = (Resolve-Path -LiteralPath 'C:\Users\54177\Desktop\BestFGS').Path
$backupRoot = Join-Path 'C:\Users\54177\Documents\ChatGPT\mcts\tmp' ('BestFGS-before-20260914-' + (Get-Date -Format 'HHmmss-fff'))
$files = @(
    'benchmark_metrics.py', 'run_swebench.py', 'run_terminal_bench.py',
    'refresh_experiment_reports.py', 'README.md', 'CHANGES_20260914.md',
    'src\cli_retrac_mcts\__main__.py',
    'src\cli_retrac_mcts\best_first.py', 'src\cli_retrac_mcts\environment.py',
    'src\cli_retrac_mcts\mcts.py', 'src\cli_retrac_mcts\models.py',
    'src\cli_retrac_mcts\retrac_adapter.py', 'src\cli_retrac_mcts\success_judge.py',
    'tests\test_benchmark_runners.py', 'tests\test_best_first.py',
    'tests\test_environment.py', 'tests\test_retrac_adapter.py', 'tests\test_success_judge.py',
    'benchmark_results\reconciled\official-interaction-summary-best-fgs-swe-12-20260913-011145-189893.json',
    'benchmark_results\reconciled\official-interaction-summary-best-fgs-tb2-8-20260913-010737-108825.json'
)
$plan = foreach ($relative in $files) {
    $sourcePath = [IO.Path]::GetFullPath((Join-Path $sourceRoot $relative))
    $targetPath = [IO.Path]::GetFullPath((Join-Path $targetRoot $relative))
    if (!$sourcePath.StartsWith($sourceRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
        !$targetPath.StartsWith($targetRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escaped project: $relative"
    }
    if (!(Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw "Missing source: $relative" }
    [pscustomobject]@{
        Relative = $relative; Source = $sourcePath; Target = $targetPath
        OldHash = if (Test-Path -LiteralPath $targetPath) { (Get-FileHash -LiteralPath $targetPath).Hash } else { $null }
        NewHash = (Get-FileHash -LiteralPath $sourcePath).Hash
    }
}
New-Item -ItemType Directory -Path $backupRoot | Out-Null
foreach ($entry in $plan) {
    if ($entry.OldHash) {
        if ((Get-FileHash -LiteralPath $entry.Target).Hash -ne $entry.OldHash) { throw 'Concurrent target change detected' }
        $backupPath = Join-Path $backupRoot $entry.Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupPath) | Out-Null
        Copy-Item -LiteralPath $entry.Target -Destination $backupPath
    } elseif (Test-Path -LiteralPath $entry.Target) { throw 'Concurrent target creation detected' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $entry.Target) | Out-Null
    Copy-Item -LiteralPath $entry.Source -Destination $entry.Target -Force
    if ((Get-FileHash -LiteralPath $entry.Target).Hash -ne $entry.NewHash) { throw 'Copy hash mismatch' }
    Write-Output ('Synced: ' + $entry.Relative)
}
Write-Output ('Backup: ' + $backupRoot)
