import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import AreaBackgroundWrapper from "@/components/AreaBackgroundWrapper";
import Footer from "@/components/Footer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "LeadLock - Cheshire Stables Sales Control",
  description: "Premium lead management system for Cheshire Stables",
  applicationName: "LeadLock",
  appleWebApp: {
    capable: true,
    title: "LeadLock",
    statusBarStyle: "default",
  },
  // Favicon + apple touch: app/icon.png and app/apple-icon.png (Next.js metadata file convention)
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Match :root --background on first paint (reduces iOS home-screen launch flash)
  themeColor: "#FAFAFA",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="bg-background">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background`}
      >
        <AreaBackgroundWrapper>
          <div className="flex min-h-screen flex-col">
            <div className="flex-1">{children}</div>
            <Footer />
          </div>
          <Toaster />
        </AreaBackgroundWrapper>
      </body>
    </html>
  );
}
