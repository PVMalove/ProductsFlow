const API_BASE_URL = "http://localhost:8000";

const PRODUCTS_URL =
  `${API_BASE_URL}/api/v2/products/featured?count=12`;

const productsContainer =
  document.getElementById("products");

function formatPrice(price) {
  return new Intl.NumberFormat(
    "ru-RU",
    {
      style: "currency",
      currency: "RUB",
      maximumFractionDigits: 0,
    }
  ).format(price);
}

function createProductCard(product, imageUrl) {
  return `
    <article class="product-card">
      <img
        class="product-image"
        src="${imageUrl}"
        alt="${product.name}"
        loading="lazy"
      />

      <div class="product-content">
        <div class="product-category">
          ${product.category}
        </div>

        <h2 class="product-name">
          ${product.name}
        </h2>

        <p class="product-description">
          ${product.description}
        </p>

        <div class="product-footer">
          <div class="product-price">
            ${formatPrice(product.price)}
          </div>

          <div class="product-id">
            #${product.id}
          </div>
        </div>
      </div>
    </article>
  `;
}

async function loadProducts() {
  productsContainer.innerHTML =
    `<div class="loader">Загрузка товаров...</div>`;

  try {
    const response = await fetch(PRODUCTS_URL);

    if (!response.ok) {
      throw new Error(
        `HTTP error ${response.status}`
      );
    }

    const data = await response.json();

    const productsWithImages = data.map((product) =>
      createProductCard(
        product,
        product.image_url ||
          "https://placehold.co/600x400/111827/ffffff?text=No+Image"
      )
    );

    productsContainer.innerHTML =
      productsWithImages.join("");

  } catch (error) {
    console.error(error);

    productsContainer.innerHTML = `
      <div class="loader error">
        Не удалось загрузить товары
      </div>
    `;
  }
}

loadProducts();
