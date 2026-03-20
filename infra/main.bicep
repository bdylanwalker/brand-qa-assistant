targetScope = 'resourceGroup'

@description('Environment name used to name all resources')
param environmentName string

@description('Azure region for all resources')
param location string = resourceGroup().location

// Shared tags applied to every resource
var tags = {
  environment: environmentName
  project: 'brand-qa-assistant'
}

var abbrs = {
  containerRegistry: 'acr'
  containerApp: 'ca'
  containerAppEnv: 'cae'
  aiHub: 'aih'
  aiProject: 'aip'
  storage: 'st'
  keyVault: 'kv'
}

var resourceToken = toLower(uniqueString(resourceGroup().id, environmentName))

// ---------------------------------------------------------------------------
// Container Registry
// ---------------------------------------------------------------------------
module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  params: {
    name: '${abbrs.containerRegistry}${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Storage (brand PDFs source)
// ---------------------------------------------------------------------------
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: '${abbrs.storage}${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Key Vault
// ---------------------------------------------------------------------------
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    name: '${abbrs.keyVault}-${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Azure AI Foundry (AI Services account + Project + gpt-4o-mini deployment)
// ---------------------------------------------------------------------------
module aiFoundry 'modules/ai-foundry.bicep' = {
  name: 'ai-foundry'
  params: {
    hubName: '${abbrs.aiHub}-${resourceToken}'
    projectName: '${abbrs.aiProject}-${resourceToken}'
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Container App Environment + App
// ---------------------------------------------------------------------------
module containerApp 'modules/container-app.bicep' = {
  name: 'container-app'
  params: {
    envName: '${abbrs.containerAppEnv}-${resourceToken}'
    appName: '${abbrs.containerApp}-${resourceToken}'
    location: location
    tags: tags
    containerRegistryServer: containerRegistry.outputs.loginServer
    projectEndpoint: aiFoundry.outputs.projectEndpoint
    blobAccountUrl: storage.outputs.primaryEndpoint
    storageAccountResourceId: storage.outputs.resourceId
  }
}

// ---------------------------------------------------------------------------
// Grant Container App identity Azure AI Developer access on AI Services
// ---------------------------------------------------------------------------
resource aiDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, '${abbrs.containerApp}-${resourceToken}', 'azure-ai-developer')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '64702f94-c441-49e6-a78b-ef80e0188fee' // Azure AI Developer
    )
    principalId: containerApp.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Grant Container App identity access to Key Vault
// ---------------------------------------------------------------------------
module kvAccess 'modules/keyvault.bicep' = {
  name: 'keyvault-access'
  params: {
    name: keyVault.outputs.name
    location: location
    tags: tags
    containerAppPrincipalId: containerApp.outputs.principalId
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
output containerRegistryLoginServer string = containerRegistry.outputs.loginServer
output containerAppFqdn string = containerApp.outputs.fqdn
output storageAccountName string = storage.outputs.name
output keyVaultName string = keyVault.outputs.name
output aiProjectEndpoint string = aiFoundry.outputs.projectEndpoint
