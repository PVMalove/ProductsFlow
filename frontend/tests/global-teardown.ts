import { execSync } from 'child_process'
import path from 'path'

export default async function globalTeardown() {
  console.log('Tearing down productsflow-e2e Gateway...')
  const backendDir = path.resolve(__dirname, '../../backend')
  
  try {
    execSync(
      'docker compose -p productsflow-e2e -f docker-compose.yml -f docker-compose.e2e.yml down -v',
      { cwd: backendDir, stdio: 'inherit' }
    )
    console.log('Gateway teardown complete.')
  } catch (error) {
    console.error('Failed to teardown Gateway', error)
  }
}
