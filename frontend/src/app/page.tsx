import Link from 'next/link';
import {
  BookOpen,
  ChevronRight,
  Grid2X2,
  House,
  Laptop,
  PackageSearch,
  Shirt,
  ShoppingCart,
  Sparkles,
  Trophy,
} from 'lucide-react';

const CATEGORIES = [
  { name: 'Бытовая техника', count: '25 товаров', icon: PackageSearch },
  { name: 'Одежда', count: '20 товаров', icon: Shirt },
  { name: 'Электроника', count: '19 товаров', icon: Laptop },
  { name: 'Дом и сад', count: '17 товаров', icon: House },
  { name: 'Спорт', count: '14 товаров', icon: Trophy },
  { name: 'Книги', count: '10 товаров', icon: BookOpen },
];

function StorefrontPreview() {
  return (
    <div className="relative mx-auto w-full max-w-md">
      <div className="absolute -right-2 -top-3 grid size-11 place-items-center rounded-full border border-blue-300/30 bg-blue-600 text-white shadow-lg shadow-blue-950/30">
        <ShoppingCart size={19} strokeWidth={1.8} />
      </div>
      <div className="overflow-hidden rounded-lg border border-white/10 bg-[#252d36] shadow-2xl shadow-black/25">
        <div className="grid grid-cols-3 gap-2 border-b border-white/8 p-4">
          {['bg-blue-500', 'bg-emerald-500', 'bg-amber-500'].map((color) => (
            <div key={color} className="rounded-md bg-[#2d3540] p-2.5">
              <div className={`h-9 rounded-sm ${color} opacity-85`} />
              <div className="mt-2 h-1 w-8 rounded-full bg-slate-300/80" />
              <div className="mt-1 h-1 w-5 rounded-full bg-slate-500" />
            </div>
          ))}
        </div>
        <div className="space-y-2 p-4">
          <div className="h-1.5 w-full rounded-full bg-slate-600/60" />
          <div className="h-1.5 w-4/5 rounded-full bg-slate-700" />
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main>
      <section className="border-b border-white/5 bg-[linear-gradient(110deg,#1d2b3f_0%,#1f3a62_53%,#1d2a3b_100%)]">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[1.1fr_.9fr] lg:items-center lg:gap-16 lg:py-20">
          <div>
            <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
              <Sparkles size={13} className="text-blue-400" />
              Магазин ProductsFlow
            </div>
            <h1 className="max-w-md text-4xl font-extrabold leading-[1.08] tracking-tight text-slate-100 sm:text-5xl">
              Товары, которые приятно искать
            </h1>
            <p className="mt-4 max-w-md text-sm leading-6 text-slate-300">
              Каталог из шести категорий, прозрачные цены и простой поиск. Всё, что нужно для выбора — в одном месте.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/catalog" className="inline-flex h-9 items-center gap-2 rounded-md bg-blue-600 px-4 text-xs font-semibold text-white shadow-lg shadow-blue-950/30 transition hover:bg-blue-500">
                <Grid2X2 size={15} />
                Смотреть каталог
              </Link>
              <Link href="/login" className="inline-flex h-9 items-center gap-2 rounded-md border border-blue-400/70 px-4 text-xs font-semibold text-blue-100 transition hover:border-blue-300 hover:bg-blue-400/10">
                Войти
              </Link>
            </div>
          </div>
          <StorefrontPreview />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-12">
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-bold tracking-tight text-slate-100">Категории</h2>
          <span className="text-xs text-slate-400">Выберите, чтобы отфильтровать</span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {CATEGORIES.map(({ name, count, icon: Icon }) => (
            <Link
              key={name}
              href={`/catalog?category=${encodeURIComponent(name)}`}
              className="group flex min-h-16 items-center gap-3 rounded-md border border-white/10 bg-[#282f37] px-3.5 transition hover:-translate-y-0.5 hover:border-blue-400/60 hover:bg-[#2c3745]"
            >
              <span className="grid size-8 place-items-center rounded-md bg-blue-500/10 text-cyan-400 transition group-hover:bg-blue-500/20">
                <Icon size={17} strokeWidth={1.7} />
              </span>
              <span>
                <span className="block text-xs font-semibold text-slate-100">{name}</span>
                <span className="block pt-0.5 text-[11px] text-slate-400">{count}</span>
              </span>
              <ChevronRight size={16} className="ml-auto text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-blue-300" />
            </Link>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-16 sm:px-8">
        <div className="rounded-lg border border-blue-400/15 bg-[linear-gradient(120deg,rgba(28,60,99,.5),rgba(38,46,55,.75))] p-6 sm:flex sm:items-center sm:justify-between sm:p-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-blue-300">Быстрый поиск</p>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">Начните с полного каталога</h2>
            <p className="mt-2 text-sm text-slate-300">Фильтруйте товары по названию, категории и цене.</p>
          </div>
          <Link href="/catalog" className="mt-5 inline-flex h-9 items-center gap-1 rounded-md bg-blue-600 px-4 text-xs font-semibold text-white transition hover:bg-blue-500 sm:mt-0">
            Перейти к товарам <ChevronRight size={15} />
          </Link>
        </div>
      </section>
    </main>
  );
}
