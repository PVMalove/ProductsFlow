import Link from 'next/link';

const CATEGORIES = [
  'electronics',
  'clothing',
  'books',
  'home',
  'sports',
  'toys',
];

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center p-8 bg-zinc-50 dark:bg-black text-black dark:text-zinc-50">
      <div className="w-full max-w-4xl py-20 text-center flex flex-col items-center justify-center">
        <h1 className="text-5xl font-extrabold tracking-tight mb-6">Welcome to ProductsFlow</h1>
        <p className="text-xl text-gray-500 mb-10 max-w-2xl">
          Discover the best products across various categories. Built with performance and user experience in mind.
        </p>
        <Link href="/catalog" className="px-8 py-3 bg-black text-white dark:bg-white dark:text-black rounded-full font-semibold hover:opacity-90 transition-opacity">
          Browse All Products
        </Link>
      </div>

      <div className="w-full max-w-4xl mt-12">
        <h2 className="text-2xl font-bold mb-6">Shop by Category</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {CATEGORIES.map((category) => (
            <Link 
              key={category} 
              href={`/catalog?category=${category}`}
              className="p-6 border rounded-xl flex items-center justify-center text-lg font-medium hover:border-black dark:hover:border-white transition-colors bg-white dark:bg-zinc-900 shadow-sm hover:shadow-md"
            >
              <span className="capitalize">{category}</span>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
