param(
  [string]$ApiBase = "http://localhost:4080",
  [string]$AdminEmail = "admin@example.com",
  [string]$AdminPassword = "Admin123!Pass",
  [string]$ProviderName = "NewAPI Telecom",
  [string]$BaseUrl = "https://provider.example/v1",
  [string]$ChatModel = "nvidia/nemotron-3-ultra-550b-a55b:free",
  [string]$EmbeddingModel = "Qwen3-Embedding-0.6B",
  [string]$RerankerModel = "Qwen3-Reranker-0.6B",
  [switch]$SetChatCompletions,
  [switch]$ConfigureExistingProjects,
  [switch]$SeedPricing
)

$ErrorActionPreference = "Stop"

$ApiBase = $ApiBase.TrimEnd("/")
$ApiKey = $env:NEWAPI_API_KEY
if (-not $ApiKey) {
  $ApiKey = $env:NEWAPI_KEY
}
if (-not $ApiKey) {
  throw "Set NEWAPI_API_KEY or NEWAPI_KEY in the current shell before running this script."
}

$login = Invoke-RestMethod `
  -Method Post `
  -Uri "$ApiBase/api/auth/login" `
  -ContentType "application/json" `
  -Body (@{
    email = $AdminEmail
    password = $AdminPassword
  } | ConvertTo-Json)

$headers = @{ Authorization = "Bearer $($login.token)" }

$providers = Invoke-RestMethod -Method Get -Uri "$ApiBase/api/admin/providers" -Headers $headers
$provider = @($providers | Where-Object { $_.name -eq $ProviderName } | Select-Object -First 1)
$providerBody = @{
  name = $ProviderName
  provider = "openai_compatible"
  api_key = $ApiKey
  base_url = $BaseUrl
  is_active = $true
  priority = 100
}

if ($provider) {
  $provider = Invoke-RestMethod `
    -Method Put `
    -Uri "$ApiBase/api/admin/providers/$($provider.id)" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body ($providerBody | ConvertTo-Json)
} else {
  $provider = Invoke-RestMethod `
    -Method Post `
    -Uri "$ApiBase/api/admin/providers" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body ($providerBody | ConvertTo-Json)
}

$modelRoutes = @(
  @{ route = "models"; model = $ChatModel },
  @{ route = "embedding-models"; model = $EmbeddingModel },
  @{ route = "reranker-models"; model = $RerankerModel }
)

foreach ($item in $modelRoutes) {
  Invoke-RestMethod `
    -Method Post `
    -Uri "$ApiBase/api/admin/providers/$($provider.id)/$($item.route)" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body (@{ model = $item.model } | ConvertTo-Json) | Out-Null
}

# --- Seed pricing rules for registered models ---
# Creates zero-cost TOKEN pricing rules so models appear as "priced" in the
# pricing catalog instead of "unpriced".  Skip this when rules already exist
# (the API returns 400 for duplicates, which we silently ignore).
if ($SeedPricing) {
  $pricingSeeds = @(
    @{ model = $ChatModel;     input_price = 0; output_price = 0 },
    @{ model = $EmbeddingModel; input_price = 0; output_price = 0 },
    @{ model = $RerankerModel;  input_price = 0; output_price = 0 }
  )

  foreach ($seed in $pricingSeeds) {
    try {
      Invoke-RestMethod `
        -Method Post `
        -Uri "$ApiBase/api/admin/pricing" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body (@{
          model        = $seed.model
          billing_mode = "TOKEN"
          input_price  = $seed.input_price
          output_price = $seed.output_price
          token_unit   = 1000000
          is_active    = $true
        } | ConvertTo-Json) | Out-Null
      Write-Host "  [pricing] Created rule for $($seed.model)" -ForegroundColor Green
    } catch {
      # 400 = rule already exists, which is fine
      $statusCode = $null
      if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $statusCode = $_.Exception.Response.StatusCode.value__
      }
      if ($statusCode -eq 400) {
        Write-Host "  [pricing] Rule already exists for $($seed.model), skipping" -ForegroundColor Yellow
      } else {
        throw "Failed to create pricing rule for $($seed.model): $_"
      }
    }
  }
}

if ($SetChatCompletions) {
  $runtimeConfig = Invoke-RestMethod -Method Get -Uri "$ApiBase/api/admin/llm-runtime-config" -Headers $headers
  $runtimeConfig.llm_openai_api_style = "chat_completions"
  Invoke-RestMethod `
    -Method Put `
    -Uri "$ApiBase/api/admin/llm-runtime-config" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body ($runtimeConfig | ConvertTo-Json -Depth 20) | Out-Null
}

$configuredProjectCount = 0
if ($ConfigureExistingProjects) {
  $chatComponentKeys = @(
    "default",
    "operation_create",
    "operation_continue",
    "operation_agent_task",
    "operation_agent_suggest",
    "operation_consistency_check",
    "operation_analyze",
    "operation_rewrite",
    "operation_summarize",
    "ontology_generation",
    "memory_build"
  )

  $page = 1
  do {
    $projects = @(Invoke-RestMethod -Method Get -Uri "$ApiBase/api/projects?page=$page&page_size=100" -Headers $headers)
    foreach ($project in $projects) {
      $componentModels = @{}
      if ($project.component_models) {
        foreach ($prop in $project.component_models.PSObject.Properties) {
          if ($prop.Value) {
            $componentModels[$prop.Name] = [string]$prop.Value
          }
        }
      }
      foreach ($key in $chatComponentKeys) {
        $componentModels[$key] = $ChatModel
      }
      $componentModels["memory_embedding"] = $EmbeddingModel
      $componentModels["memory_reranker"] = $RerankerModel

      Invoke-RestMethod `
        -Method Put `
        -Uri "$ApiBase/api/projects/$($project.id)" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body (@{ component_models = $componentModels } | ConvertTo-Json -Depth 20) | Out-Null
      $configuredProjectCount += 1
    }
    $page += 1
  } while ($projects.Count -eq 100)
}

$result = Invoke-RestMethod -Method Get -Uri "$ApiBase/api/admin/providers" -Headers $headers
$providerResult = $result |
  Where-Object { $_.name -eq $ProviderName } |
  Select-Object id, name, provider, base_url, models, embedding_models, reranker_models, is_active, priority

if ($ConfigureExistingProjects) {
  $providerResult | Add-Member -NotePropertyName configured_project_count -NotePropertyValue $configuredProjectCount
}

$providerResult |
  ConvertTo-Json -Depth 10
