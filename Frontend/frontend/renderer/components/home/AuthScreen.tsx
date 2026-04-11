import Head from "next/head";

import { SignInPage, Testimonial } from "../ui/sign-in";




interface AuthScreenProps {
  authMode: "login" | "register";
  notice?: string | null;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  onOAuth: (provider: "google" | "github") => Promise<void>;
  onToggleMode: () => void;
  oauthProviders: {
    google: boolean;
    github: boolean;
  };
}


export const AuthScreen = ({ authMode, notice, onSubmit, onOAuth, onToggleMode, oauthProviders }: AuthScreenProps) => (
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

      onSignIn={onSubmit}
      onGoogleSignIn={() => onOAuth("google")}
      onGitHubSignIn={() => onOAuth("github")}
      onToggleMode={onToggleMode}
      oauthProviders={oauthProviders}
    />
  </div>
);
