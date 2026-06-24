import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/lib/query-client";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { PageTransition } from "@/components/shell/PageTransition";
import { Toaster } from "@/components/shell/Toaster";
import { PlanWatcher } from "@/components/shell/PlanWatcher";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Coach Chess",
  description: "Personal chess coach",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full" suppressHydrationWarning>
        <Providers>
          <PlanWatcher />
          <Toaster />
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex-1 min-w-0 flex flex-col">
              <TopBar />
              <main className="flex-1 min-w-0">
                <PageTransition>{children}</PageTransition>
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
