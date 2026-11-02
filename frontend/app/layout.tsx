import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "OncoEvidence AI",
  description: "Clinical literature discovery and evidence synthesis workspace"
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
