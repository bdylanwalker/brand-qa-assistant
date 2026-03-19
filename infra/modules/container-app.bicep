param envName string
param appName string
param location string
param tags object
param containerRegistryServer string
param projectEndpoint string
param blobAccountUrl string
param storageAccountResourceId string

// Container App Environment (managed)
resource appEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    zoneRedundant: false
  }
}

// Container App with system-assigned managed identity
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: appEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
      }
      // Registry configured by app pipeline on first deploy via:
      // az containerapp registry set --server <acr>.azurecr.io --identity system
      registries: []
      secrets: []
    }
    template: {
      containers: [
        {
          name: 'brand-qa-assistant'
          // Placeholder image for initial infra deploy. The app pipeline replaces
          // this with the real image via: az containerapp update --image ...
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            {
              name: 'PROJECT_ENDPOINT'
              value: projectEndpoint
            }
            {
              name: 'BLOB_ACCOUNT_URL'
              value: blobAccountUrl
            }
            {
              name: 'MODEL_DEPLOYMENT'
              value: 'gpt-4o-mini'
            }
            {
              // Set via Key Vault after bootstrap: az containerapp secret set ...
              name: 'VECTOR_STORE_ID'
              value: ''
            }
            {
              // Set via Key Vault after bootstrap: az containerapp secret set ...
              name: 'AGENT_ID'
              value: ''
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// Grant AcrPull role to the Container App managed identity on the registry
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, containerRegistryServer, 'acr-pull')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Grant Storage Blob Data Reader role to the Container App managed identity
resource blobReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, storageAccountResourceId, 'blob-data-reader')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' // Storage Blob Data Reader
    )
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output principalId string = containerApp.identity.principalId
output name string = containerApp.name
