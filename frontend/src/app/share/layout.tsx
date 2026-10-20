import type { Metadata } from "next";
import React from "react";

export const metadata: Metadata = {
  title: "Secure Medical Report Sharing",
  referrer: "no-referrer",
  robots: {
    index: false,
    follow: false,
  },
};

export default function ShareLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <meta name="referrer" content="no-referrer" />
      {children}
    </>
  );
}
