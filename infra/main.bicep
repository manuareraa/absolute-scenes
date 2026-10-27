// Absolute Scenes Azure core for the Analyst MCP server: one consumption-only Container Apps
// environment and the `mcp` Container App, image from GHCR. Deployed by the coordinator only
// (see docs/notes/d-azure-deploy.md); CI only compiles this file.
//
// Budget guard rails ($100 credit for the whole project):
// - no workloadProfiles: the environment is consumption-only, no base fee;
// - minReplicas 0, maxReplicas 1, 0.25 vCPU / 0.5 GiB: billed only while serving, inside the free grant;
// - no ACR (images come from GHCR) and no Log Analytics unless a workspace with a daily cap is passed in.
targetScope = 'resourceGroup'

@description('Region. The subscription allows koreacentral, polandcentral, malaysiawest, eastasia, indiasouthcentral.')
@allowed(['koreacentral', 'polandcentral', 'malaysiawest', 'eastasia', 'indiasouthcentral'])
param location string = 'koreacentral'

@description('Container Apps environment name.')
param environmentName string = 'chalktalk-cae'

@description('Container App name.')
param appName string = 'chalktalk-mcp'

@description('Image to run. Pin a sha-<short> tag for demos.')
param image string = 'ghcr.io/manuareraa/chalktalk-mcp:latest'

@description('GHCR user for a private package. Leave empty when the package is public.')
param registryUsername string = ''

@description('GHCR read-only token (read:packages) for a private package. Never commit it.')
@secure()
param registryPassword string = ''

@description('Public ingress. The MCP server has no auth of its own, so restrict it with allowedCidrs.')
param externalIngress bool = true

@description('CIDRs allowed to reach the app (for example the coordinator machine, "203.0.113.7/32"). Empty means no IP restriction.')
param allowedCidrs array = []

@description('Optional Log Analytics workspace (customerId) for app logs. Empty means logs are not stored.')
param logAnalyticsCustomerId string = ''

@description('Shared key of that workspace.')
@secure()
param logAnalyticsSharedKey string = ''

@description('Half length in minutes used when the server regenerates a sim-<seed> match; must match the package the Worker serves.')
param simHalfMinutes string = '5'

var useRegistryAuth = !empty(registryUsername) && !empty(registryPassword)
var useLogs = !empty(logAnalyticsCustomerId) && !empty(logAnalyticsSharedKey)
var tags = { project: 'chalktalk', stream: 'd' }

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    // No workloadProfiles: consumption-only.
    appLogsConfiguration: useLogs
      ? {
          destination: 'log-analytics'
          logAnalyticsConfiguration: {
            customerId: logAnalyticsCustomerId
            sharedKey: logAnalyticsSharedKey
          }
        }
      : null
    zoneRedundant: false
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  properties: {
    environmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: externalIngress
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        ipSecurityRestrictions: [
          for (cidr, i) in allowedCidrs: {
            name: 'allow-${i}'
            action: 'Allow'
            ipAddressRange: cidr
          }
        ]
      }
      secrets: useRegistryAuth ? [{ name: 'ghcr-password', value: registryPassword }] : []
      registries: useRegistryAuth
        ? [
            {
              server: 'ghcr.io'
              username: registryUsername
              passwordSecretRef: 'ghcr-password'
            }
          ]
        : []
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: image
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            // One generated match in memory fits in 0.5 GiB (a 2 x 45 min match is about 65 MB).
            { name: 'CHALKTALK_MAX_MATCHES', value: '1' }
            { name: 'CHALKTALK_SIM_HALF_MINUTES', value: simHalfMinutes }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 2
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '20' } }
          }
        ]
      }
    }
  }
}

output environmentId string = env.id
output mcpUrl string = externalIngress ? 'https://${app.properties.configuration.ingress.fqdn}/mcp' : ''
output mcpFqdn string = app.properties.configuration.ingress.fqdn
