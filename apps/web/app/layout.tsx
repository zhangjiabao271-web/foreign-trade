import type { Metadata, Viewport } from "next";

import { AppProviders } from "@/components/app-providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "外贸工作台",
  description: "围绕第一笔可盈利订单构建的外贸经营系统",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
