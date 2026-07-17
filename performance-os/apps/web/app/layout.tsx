import "./globals.css";

export const metadata = {
  title: "Performance OS",
  description: "AI-powered training, recovery, and health platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-black text-white min-h-screen">{children}</body>
    </html>
  );
}
