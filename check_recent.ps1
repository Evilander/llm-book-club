Get-ChildItem 'B:\ai\llm-book' -Recurse -File -Exclude '*.pyc' |
  Where-Object { $_.FullName -notmatch 'node_modules|\.next|__pycache__|\.pytest_cache|\.venv' } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 50 @{N='File';E={$_.FullName.Replace('B:\ai\llm-book\','')}}, @{N='Modified';E={$_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')}} |
  Format-Table -AutoSize -Wrap
