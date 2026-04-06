import Head from "next/head";

import { SignInPage, Testimonial } from "../ui/sign-in";
import { UserData } from "./types";


const sampleTestimonials: Testimonial[] = [
  {
    avatarSrc: "https://randomuser.me/api/portraits/men/32.jpg",
    name: "M. Gökşin",
    handle: "Senior Unity Developer",
    text: "Unity Architect AI has completely transformed my workflow. The code audits are precise, and the local AI integration is a game-changer for latency!",
  },
  {
    avatarSrc: "https://randomuser.me/api/portraits/women/44.jpg",
    name: "Ayşe Yılmaz",
    handle: "Indie Game Dev",
    text: "Finally, an AI that understands Game Feel! It doesn't just write code; it writes code that feels good to play. Absolutely essential tool.",
  },
  {
    avatarSrc: "https://randomuser.me/api/portraits/men/68.jpg",
    name: "Burak E.",
    handle: "Lead Architect",
    text: "The Multi-Agent architecture is brilliant. Having separate agents for planning, coding, and critiquing results in enterprise-level C# scripts every time.",
  },
];


interface AuthScreenProps {
  authMode: "login" | "register";
  notice?: string | null;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  onOAuth: (provider: "google" | "github") => Promise<void>;
  onToggleMode: () => void;
}


export const AuthScreen = ({ authMode, notice, onSubmit, onOAuth, onToggleMode }: AuthScreenProps) => (
  <div className="bg-[#000000] text-foreground">
    <Head><title>Unity Architect AI | {authMode === "login" ? "Giriş" : "Kayıt"}</title></Head>
    <SignInPage
      authMode={authMode}
      notice={notice}
      title={
        <div className="mb-2">
          <span className="font-light text-slate-300 tracking-tighter">Hoş Geldiniz </span><br />
          <span className="font-extrabold text-white tracking-tight">Unity Architect <span className="text-blue-500">AI</span></span>
        </div>
      }
      description={authMode === "login" ? "Hesabınıza giriş yapın ve Unity projelerinizi geliştirmeye devam edin." : "Yeni bir hesap oluşturun ve kod kalitenizi hemen artırın."}
      heroImageSrc="https://images.unsplash.com/photo-1616499370260-485e3e5810e7?q=80&w=2160&auto=format&fit=crop"
      testimonials={sampleTestimonials}
      onSignIn={onSubmit}
      onGoogleSignIn={() => onOAuth("google")}
      onGitHubSignIn={() => onOAuth("github")}
      onToggleMode={onToggleMode}
      onResetPassword={onToggleMode}
    />
  </div>
);
