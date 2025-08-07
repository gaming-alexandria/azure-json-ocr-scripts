[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$DirectoryPath,
    
    [Parameter(Mandatory=$false)]
    [string]$Endpoint,
    
    [Parameter(Mandatory=$false)]
    [string]$ApiKey,
    
    [Parameter(Mandatory=$false)]
    [int]$MaxFiles = 0
)

# Azure Document Intelligence PDF OCR PowerShell Script
# FINAL VERSION: Combines the working PDF download method with saving the full, detailed JSON.

# Hardcoded configuration
$HARDCODED_ENDPOINT = "https://westus2.api.cognitive.microsoft.com/"
$HARDCODED_API_KEY = "[Insert Azure API Key Here]"
# --- Using the API version from your working script ---
$API_VERSION = "2024-11-30"

# --- HELPER FUNCTIONS (UNCHANGED) ---
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "$timestamp - $Level - $Message"; Write-Host $logMessage
}

function Get-PDFFiles {
    param([string]$Directory)
    if (-not (Test-Path $Directory)) { throw "Directory not found: $Directory" }
    $pdfFiles = Get-ChildItem -Path $Directory -Filter "*.pdf" -File
    Write-Log "Found $($pdfFiles.Count) PDF files in $Directory"; return $pdfFiles
}

# --- SCRIPT FUNCTIONS (FROM YOUR WORKING SCRIPT) ---

function Start-DocumentAnalysis {
    param([string]$Endpoint, [string]$ApiKey, [string]$FilePath)
    # This is the exact URL construction from your working script. We keep it.
    $uri = "$($Endpoint.TrimEnd('/'))/documentintelligence/documentModels/prebuilt-read:analyze?_overload=analyzeDocument&api-version=$API_VERSION&output=pdf"
    $headers = @{ 'Ocp-Apim-Subscription-Key' = $ApiKey; 'Content-Type' = 'application/pdf' }
    try {
        $fileBytes = [System.IO.File]::ReadAllBytes($FilePath)
        Write-Log "Starting analysis for: $(Split-Path $FilePath -Leaf)"
        $response = Invoke-WebRequest -Uri $uri -Method Post -Headers $headers -Body $fileBytes
        $operationLocation = $response.Headers['Operation-Location']
        if ([string]::IsNullOrEmpty($operationLocation)) { throw "Operation-Location header not found" }
        Write-Log "Operation Location: $operationLocation"
        return $operationLocation
    } catch { Write-Log "Error starting analysis: $($_.Exception.Message)" -Level "ERROR"; throw }
}

function Get-AnalysisResults {
    param([string]$OperationLocation, [string]$ApiKey, [int]$MaxWaitSeconds = 300)
    $headers = @{ 'Ocp-Apim-Subscription-Key' = $ApiKey }
    $startTime = Get-Date
    while (((Get-Date) - $startTime).TotalSeconds -lt $MaxWaitSeconds) {
        Start-Sleep -Seconds 5
        try {
            $response = Invoke-RestMethod -Uri $OperationLocation -Method Get -Headers $headers
            Write-Log "Analysis status: $($response.status)"
            if ($response.status -eq "succeeded") { return $response }
            if ($response.status -eq "failed") { throw "Analysis failed: $($response.error.message)" }
        } catch { Write-Log "Error checking analysis status: $($_.Exception.Message)" -Level "ERROR"; throw }
    }
    throw "Analysis timed out after $MaxWaitSeconds seconds"
}

function Get-SearchablePDF {
    param([string]$OperationLocation, [string]$ApiKey, [string]$OutputPath)
    # This is the exact PDF download logic from your working script. We keep it.
    $pdfUri = $OperationLocation -replace '\?.*', "/pdf?api-version=$API_VERSION"
    $headers = @{ 'Ocp-Apim-Subscription-Key' = $ApiKey }
    try {
        Write-Log "Attempting to download searchable PDF from: $pdfUri"
        $webClient = New-Object System.Net.WebClient
        foreach ($header in $headers.Keys) { $webClient.Headers.Add($header, $headers[$header]) }
        $webClient.DownloadFile($pdfUri, $OutputPath)
        $webClient.Dispose()
        if (Test-Path $OutputPath) {
            Write-Log "Successfully downloaded searchable PDF to: $OutputPath"
            return $true
        } else {
            Write-Log "Download appeared to succeed but file not found: $OutputPath" -Level "ERROR"
            return $false
        }
    } catch {
        if ($webClient) { $webClient.Dispose() }
        Write-Log "Error downloading searchable PDF: $($_.Exception.Message)" -Level "WARNING"
        return $false
    }
}

# --- MODIFIED Process-PDF Function ---
# This is the only function that has been changed.
function Process-PDF {
    param(
        [string]$FilePath,
        [string]$Endpoint,
        [string]$ApiKey
    )
    
    try {
        Write-Log "Processing: $(Split-Path $FilePath -Leaf)"
        
        # Start analysis and get the complete result object. This is unchanged.
        $operationLocation = Start-DocumentAnalysis -Endpoint $Endpoint -ApiKey $ApiKey -FilePath $FilePath
        $analysisResult = Get-AnalysisResults -OperationLocation $operationLocation -ApiKey $ApiKey
        
        $directory = Split-Path $FilePath -Parent
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
        
        # --- CHANGE #1: SAVE THE FULL JSON ---
        # Instead of calling ConvertTo-StructuredJSON, we save the raw 'analyzeResult' object.
        # This provides the complete, detailed JSON you wanted.
        try {
            Write-Log "Saving FULL detailed JSON result..."
            $jsonPath = Join-Path $directory "$baseName.json" # Use a simple name like the original script
            $analysisResult.analyzeResult | ConvertTo-Json -Depth 20 | Set-Content -Path $jsonPath -Encoding utf8
            Write-Log "Saved full JSON result to: $jsonPath"
        }
        catch {
            Write-Log "Error saving full JSON result: $($_.Exception.Message)" -Level "ERROR"
        }
        
        # --- CHANGE #2: DOWNLOAD THE PDF (LOGIC UNCHANGED) ---
        # This block is the same as before, ensuring the PDF download continues to work.
        Write-Log "Downloading searchable PDF..."
        $searchablePDFPath = Join-Path $directory "$baseName`_searchable.pdf"
        $pdfDownloadSuccess = Get-SearchablePDF -OperationLocation $operationLocation -ApiKey $ApiKey -OutputPath $searchablePDFPath
        
        if ($pdfDownloadSuccess) {
            Write-Log "Searchable PDF saved successfully"
        } else {
            Write-Log "No searchable PDF generated for: $(Split-Path $FilePath -Leaf)" -Level "WARNING"
        }
        
        Write-Log "Successfully processed: $(Split-Path $FilePath -Leaf)"
        return $true
    }
    catch {
        Write-Log "Failed to process $(Split-Path $FilePath -Leaf): $($_.Exception.Message)" -Level "ERROR"
        return $false
    }
}

# --- Main execution (Unchanged) ---
try {
    if ([string]::IsNullOrEmpty($DirectoryPath)) { $DirectoryPath = (Get-Location).Path }
    if ([string]::IsNullOrEmpty($Endpoint)) { $Endpoint = $HARDCODED_ENDPOINT }
    if ([string]::IsNullOrEmpty($ApiKey)) { $ApiKey = $HARDCODED_API_KEY }
    
    Write-Log "Starting Azure Document Intelligence PDF OCR processing..."
    Write-Log "Directory: $DirectoryPath"
    
    if ([string]::IsNullOrEmpty($Endpoint) -or [string]::IsNullOrEmpty($ApiKey)) {
        throw "Endpoint and ApiKey are required."
    }
    
    $pdfFiles = Get-PDFFiles -Directory $DirectoryPath
    if ($pdfFiles.Count -eq 0) {
        Write-Log "No PDF files found." -Level "WARNING"; exit 0
    }
    
    if ($MaxFiles -gt 0 -and $pdfFiles.Count -gt $MaxFiles) {
        $pdfFiles = $pdfFiles | Select-Object -First $MaxFiles
        Write-Log "Limited to processing $MaxFiles files"
    }
    
    $successCount = 0
    foreach ($file in $pdfFiles) {
        if (Process-PDF -FilePath $file.FullName -Endpoint $Endpoint -ApiKey $ApiKey) {
            $successCount++
        }
    }
    
    Write-Log "Processing complete! Successfully processed: $successCount files"
    if ($successCount -lt $pdfFiles.Count) { exit 1 }
}
catch {
    Write-Log "Script failed: $($_.Exception.Message)" -Level "ERROR"
    exit 1
}

# NOTE: The functions 'ConvertTo-StructuredJSON' and 'Save-Results' from your original script
# are no longer needed and have been removed for clarity.