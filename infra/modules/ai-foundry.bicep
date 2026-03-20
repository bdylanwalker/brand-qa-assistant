param hubName string
param projectName string
param location string
param tags object

// AI Services account — the backing resource for all AI Foundry APIs
resource aiServices 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: '${hubName}-aiservices'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: hubName
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

// AI Foundry Project — native CognitiveServices sub-resource.
// Creates the project at: https://<subdomain>.services.ai.azure.com/api/projects/<name>
// Note: the Hub+Project Azure ML workspaces previously in this file did not register
// a project on the services.ai.azure.com endpoint. This resource does.
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-10-01-preview' = {
  parent: aiServices
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
  }
}

// gpt-4o-mini deployment
resource gpt4oMiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: aiServices
  name: 'gpt-4o-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: 50  // TPM in thousands; adjust based on quota
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
  }
}

output projectEndpoint string = 'https://${hubName}.services.ai.azure.com/api/projects/${projectName}'
output aiServicesName string = aiServices.name
output aiServicesId string = aiServices.id
