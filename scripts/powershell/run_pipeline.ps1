param(
    [string]$Model = "llama3.2",
    [string]$Profile = "code_generate"
)

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $baseDir "..\..")
$promptDir = Join-Path $projectRoot ("prompts\profiles\{0}\pipeline" -f $Profile)

if (-not (Test-Path $promptDir)) {
    Write-Error "Prompt-Profil nicht gefunden: $promptDir"
    exit 1
}

$inputText = Read-Host "Eingabe"

$analyseTemplate = [System.IO.File]::ReadAllText((Join-Path $promptDir "01_analyse.txt"))
$loesungTemplate = [System.IO.File]::ReadAllText((Join-Path $promptDir "02_loesung.txt"))
$codeTemplate = [System.IO.File]::ReadAllText((Join-Path $promptDir "03_code.txt"))

$analysePrompt = $analyseTemplate.Replace("[HIER TEXT EINFÜGEN]", $inputText)
$analyseBody = @{ model=$Model; prompt=$analysePrompt; stream=$false } | ConvertTo-Json
$analyseResponse = (Invoke-RestMethod -Method Post -Uri "http://localhost:11434/api/generate" -ContentType "application/json; charset=utf-8" -Body $analyseBody).response
$finalTaskLine1 = ($analyseResponse -split "`n" | Where-Object { $_ -match "FINAL_TASK:" } | Select-Object -Last 1)
$finalTask1 = $finalTaskLine1 -replace '^FINAL_TASK:\s*', ''

$loesungPrompt = $loesungTemplate.Replace("[FINAL_TASK]", $finalTask1)
$loesungBody = @{ model=$Model; prompt=$loesungPrompt; stream=$false } | ConvertTo-Json
$loesungResponse = (Invoke-RestMethod -Method Post -Uri "http://localhost:11434/api/generate" -ContentType "application/json; charset=utf-8" -Body $loesungBody).response
$finalTaskLine2 = ($loesungResponse -split "`n" | Where-Object { $_ -match "FINAL_TASK:" } | Select-Object -Last 1)
$finalTask2 = $finalTaskLine2 -replace '^FINAL_TASK:\s*', ''

$codePrompt = $codeTemplate.Replace("[FINAL_TASK]", $finalTask2)
$codeBody = @{ model=$Model; prompt=$codePrompt; stream=$false } | ConvertTo-Json
$codeResponse = (Invoke-RestMethod -Method Post -Uri "http://localhost:11434/api/generate" -ContentType "application/json; charset=utf-8" -Body $codeBody).response

Write-Host "===== ANALYSE ====="
Write-Host $analyseResponse
Write-Host ""
Write-Host "===== LÖSUNG ====="
Write-Host $loesungResponse
Write-Host ""
Write-Host "===== CODE ====="
Write-Host $codeResponse
