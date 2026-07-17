import "./globals.css";
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
} from "@clerk/nextjs";

export const metadata = {
  title: "Performance OS",
  description: "AI-powered training, recovery, and health platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en" className="dark">
        <body className="bg-black text-white min-h-screen">
          <header className="flex justify-end items-center gap-4 p-4 border-b border-neutral-900">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="px-3 py-1.5 rounded-lg bg-white text-black text-sm font-medium">
                  Sign in
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <UserButton />
            </SignedIn>
          </header>
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
