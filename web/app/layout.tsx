import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChordCat Connect",
  description: "Find musicians who hear harmony the way you do.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
