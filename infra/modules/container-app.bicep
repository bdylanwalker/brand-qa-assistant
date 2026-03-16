param envName string
param appName string
param location string
param tags object
param containerRegistryServer string
param projectEndpoint string
param keyVaultName string

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
      registries: [
        {
          server: containerRegistryServer
          identity: 'system'   // Pull from ACR using managed identity
        }
      ]
      secrets: [
        {
          name: 'vector-store-id'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/vector-store-id'
          identity: 'system'
        }
        {
          name: 'agent-id'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/agent-id'
          identity: 'system'
        }
      ]
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
              name: 'MODEL_DEPLOYMENT'
              value: 'gpt-4o-mini'
            }
            {
              name: 'VECTOR_STORE_ID'
              secretRef: 'vector-store-id'
            }
            {
              name: 'AGENT_ID'
              secretRef: 'agent-id'
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

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output principalId string = containerApp.identity.principalId
output name string = containerApp.name
