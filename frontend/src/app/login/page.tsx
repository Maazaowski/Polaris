"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/brand/logo";
import { Mascot } from "@/components/brand/mascot";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { useLogin } from "@/hooks/use-session";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ email, password });
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid email or password.");
      } else {
        setError("Could not sign in. Is the backend running?");
      }
    }
  }

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      {/* Left: the promise, the mascot, the confetti. */}
      <section className="fade-up relative flex flex-col justify-between gap-10 overflow-hidden bg-card px-8 py-10 shadow-[inset_-1px_0_0_var(--ring-card)] md:w-1/2 md:px-16 md:py-14">
        <div className="relative z-10">
          <Logo variant="primary" href={null} className="text-[18px]" />
        </div>

        <div className="relative hidden h-[320px] md:block">
          <svg aria-hidden="true" viewBox="0 0 600 340" className="absolute inset-0 h-full w-full">
            <circle cx="70" cy="60" r="34" fill="#ffcf7b" />
            <circle cx="520" cy="50" r="12" fill="#7dc4ff" />
            <path d="M480 290l22-38 22 38z" fill="#44c67f" />
            <circle cx="120" cy="280" r="10" fill="#f966ac" />
            <rect x="430" y="110" width="26" height="26" rx="8" fill="#ff5310" transform="rotate(18 443 123)" />
            <circle cx="60" cy="190" r="7" fill="#9553f9" />
            <path d="M160 120c14-22 46-22 60 0" stroke="#ff5310" strokeWidth="7" fill="none" strokeLinecap="round" />
            <circle cx="560" cy="200" r="22" fill="#44c67f" />
            <path d="M250 300l10-18 10 18z" fill="#7dc4ff" />
            <circle cx="380" cy="40" r="6" fill="#ffcf7b" />
            <circle cx="300" cy="170" r="150" fill="none" stroke="#e8e8e8" strokeDasharray="4 10" />
          </svg>
          <div className="absolute top-14 left-1/2 -translate-x-1/2">
            <Mascot size={210} />
          </div>
        </div>

        <div className="relative z-10 flex max-w-[520px] flex-col gap-4">
          <h2 className="font-display text-[34px] leading-[1.1] font-semibold tracking-[-0.035em] text-foreground md:text-[44px]">
            The first invoice pays. Every one after it is free.
          </h2>
          <p className="text-[17px] leading-[26px] text-body">
            Polaris reads a new layout once, writes a template, and runs every later invoice
            through it at no cost, balanced and traceable to the page.
          </p>
          <ul className="flex flex-col gap-2 text-[15px] font-medium text-section-suppliers">
            <li className="flex items-center gap-2.5"><span aria-hidden="true">✓</span>Templates run at $0</li>
            <li className="flex items-center gap-2.5"><span aria-hidden="true">✓</span>Every total is checked against the page</li>
            <li className="flex items-center gap-2.5"><span aria-hidden="true">✓</span>Every delivered cell points back at the PDF</li>
          </ul>
        </div>
        <span className="relative z-10 text-[12px] text-muted-foreground">Internal tool · TemForce</span>
      </section>

      {/* Right: the form. */}
      <section className="fade-up fade-up-1 flex flex-1 items-center justify-center px-6 py-12 md:px-12">
        <form onSubmit={handleSubmit} className="flex w-full max-w-[400px] flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.4px] text-foreground">Sign in</h1>
            <p className="text-muted-foreground">Use the account an admin created for you.</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-[13px] font-medium text-foreground">
              Email
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              className="h-11 text-[15px]"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-[13px] font-medium text-foreground">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              className="h-11 text-[15px]"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <p className="rounded-2xl bg-destructive-soft px-4 py-3 text-[14px] text-destructive" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" size="xl" className="w-full" disabled={login.isPending}>
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-[13px] text-muted-foreground">
            No account? Ask an admin under Settings › People.
          </p>
        </form>
      </section>
    </div>
  );
}
