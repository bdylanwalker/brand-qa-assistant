param name string
param location string
param tags object

// Set after Container App is created (grant Secrets User role)
param containerAppPrincipalId string = ''

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true   // Use Azure RBAC (not access policies)
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false    // Allow purge in dev; set true for prod
  }
}

// Placeholder secrets — updated after ingestion / bootstrap
resource vectorStoreSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'vector-store-id'
  properties: {
    value: 'PLACEHOLDER'
  }
}

resource agentIdSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'agent-id'
  properties: {
    value: 'PLACEHOLDER'
  }
}

// Grant the Container App's managed identity Secrets User access
resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(containerAppPrincipalId)) {
  name: guid(keyVault.id, containerAppPrincipalId, 'secrets-user')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
    )
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = keyVault.name
output resourceId string = keyVault.id
output uri string = keyVault.properties.vaultUri
