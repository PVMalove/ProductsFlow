import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import ReactQueryProvider from "@/providers/react-query-provider";
import { AuthSessionProvider } from "@/providers/auth-session-provider";
import { Header } from "@/components/layout/header";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ProductsFlow — каталог товаров",
  description: "Удобный каталог товаров от ProductsFlow",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ru"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ReactQueryProvider>
          <AuthSessionProvider>
            <Header />
            <main className="flex-1">
              {children}
            </main>
          </AuthSessionProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
