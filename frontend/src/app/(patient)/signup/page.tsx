"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function PatientSignupRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/patient/register");
  }, [router]);

  return (
    <div className="max-w-md mx-auto py-16 px-4 text-center">
      <div className="bg-white p-8 rounded-2xl border border-slate-200 shadow-sm space-y-3">
        <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
        <p className="text-sm text-slate-600">Redirecting to registration...</p>
      </div>
    </div>
  );
}
