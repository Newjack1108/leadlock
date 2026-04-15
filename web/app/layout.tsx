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
  // Explicit links so tabs pick up favicon even if app/icon convention is cached oddly;
  // app/icon.png + app/apple-icon.png still provide the assets.
  icons: {
    icon: [
      { url: "/icon.png", type: "image/png", sizes: "32x32" },
      { url: "/icon.png", type: "image/png", sizes: "16x16" },
    ],
    shortcut: "/icon.png",
    apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
  },
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
