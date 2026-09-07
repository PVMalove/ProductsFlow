import { execSync } from 'child_process'
import path from 'path'

export default async function globalSetup() {
  console.log('Spawning productsflow-e2e Gateway...')
  const backendDir = path.resolve(__dirname, '../../backend')
  
  // Set E2E port and docker project name
  process.env.E2E_GATEWAY_PORT = '18080'
  process.env.NEXT_PUBLIC_API_URL = `http://127.0.0.1:${process.env.E2E_GATEWAY_PORT}`
  
  try {
    execSync(
      'docker compose -p productsflow-e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --wait',
      { cwd: backendDir, stdio: 'inherit' }
    )
    console.log('Gateway spawned successfully.')
  } catch (error) {
    console.error('Failed to spawn Gateway', error)
    throw error
  }
}
