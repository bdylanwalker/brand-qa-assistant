param hubName string
param projectName string
param location string
param tags object

// AI Foundry Hub (Azure ML Workspace in hub mode)
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: hubName
    publicNetworkAccess: 'Enabled'
  }
}

// AI Foundry Project (child workspace)
resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: projectName
  location: location
  tags: tags
  kind: 'Project'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: projectName
    hubResourceId: aiHub.id
    publicNetworkAccess: 'Enabled'
  }
}

// OpenAI Services account associated with the hub
// Note: In AI Foundry, model deployments are made via the AI Services resource
// The project endpoint is the AI Services endpoint
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${hubName}-aiservices'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: hubName
    publicNetworkAccess: 'Enabled'
  }
}

// Connect the Hub to the AI Services account so the project endpoint is
// registered at https://<subdomain>.services.ai.azure.com/api/projects/<project>
resource aiServicesConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-04-01' = {
  parent: aiHub
  name: 'aiservices-connection'
  properties: {
    category: 'AIServices'
    target: aiServices.properties.endpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: aiServices.id
    }
  }
}

// gpt-4o-mini deployment
resource gpt4oMiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: aiServices
  name: 'gpt-4o-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: 10  // TPM in thousands; adjust based on quota
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
  }
}

output hubName string = aiHub.name
output projectName string = aiProject.name
output projectEndpoint string = 'https://${hubName}.services.ai.azure.com/api/projects/${projectName}'
output aiServicesName string = aiServices.name
