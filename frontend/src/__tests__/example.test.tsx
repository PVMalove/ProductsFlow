import '@testing-library/jest-dom'

describe('MSW Setup Test', () => {
  it('mocks an API call', async () => {
    const fetchProducts = async () => {
      const res = await fetch('/api/v1/products/search')
      return res.json()
    }

    const products = await fetchProducts()
    expect(products.data).toEqual([
      expect.objectContaining({ id: '1', name: 'Mocked Product' }),
    ])
  })
})
