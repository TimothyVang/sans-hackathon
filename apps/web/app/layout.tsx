import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Find Evil! Dashboard",
  description:
    "NES.css live dashboard for the SANS Find Evil! agent army. Tails the audit JSONL hash chain; renders Pool A / Pool B / verifier / judge / correlator as pixel-art sprites. Amendment A3.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
