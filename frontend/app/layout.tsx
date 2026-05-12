import type { Metadata } from "next";
import type { ReactNode } from "react";

import { MyRuntimeProvider } from "@/components/MyRuntimeProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "TQ-Asistente",
  description:
    "Asistente conversacional sobre Tecnoquímicas S.A. y tqfarma con RAG local.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <MyRuntimeProvider>{children}</MyRuntimeProvider>
      </body>
    </html>
  );
}
