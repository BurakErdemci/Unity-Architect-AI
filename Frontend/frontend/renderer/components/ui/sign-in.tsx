import React, { useState } from 'react';
import { Eye, EyeOff, Bot, Code2, Sparkles, Cpu } from 'lucide-react';
import { motion } from 'framer-motion';

// --- HELPER COMPONENTS (ICONS) ---

const GoogleIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 48 48">
        <path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s12-5.373 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-2.641-.21-5.236-.611-7.743z" />
        <path fill="#FF3D00" d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z" />
        <path fill="#4CAF50" d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z" />
        <path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571l6.19 5.238C42.022 35.026 44 30.038 44 24c0-2.641-.21-5.236-.611-7.743z" />
    </svg>
);


const GitHubIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
    </svg>
);

// --- TYPE DEFINITIONS ---

export interface Testimonial {
  avatarSrc: string;
  name: string;
  handle: string;
  text: string;
}

interface SignInPageProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  authMode?: 'login' | 'register';
  notice?: React.ReactNode;
  heroImageSrc?: string;
  testimonials?: Testimonial[];
  onSignIn?: (event: React.FormEvent<HTMLFormElement>) => void;
  onGoogleSignIn?: () => void;
  onGitHubSignIn?: () => void;
  onToggleMode?: () => void;
  oauthProviders?: {
    google: boolean;
    github: boolean;
  };
}

// --- SUB-COMPONENTS ---

const GlassInputWrapper = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-2xl border border-border bg-foreground/5 backdrop-blur-sm transition-colors focus-within:border-violet-400/70 focus-within:bg-violet-500/10">
    {children}
  </div>
);

const TestimonialCard = ({ testimonial, delay }: { testimonial: Testimonial, delay: string }) => (
  <div className={`animate-testimonial ${delay} flex items-start gap-3 rounded-3xl bg-card/40 dark:bg-zinc-800/40 backdrop-blur-xl border border-white/10 p-5 w-64`}>
    <img src={testimonial.avatarSrc} className="h-10 w-10 object-cover rounded-2xl" alt="avatar" />
    <div className="text-sm leading-snug">
      <p className="flex items-center gap-1 font-medium">{testimonial.name}</p>
      <p className="text-muted-foreground">{testimonial.handle}</p>
      <p className="mt-1 text-foreground/80">{testimonial.text}</p>
    </div>
  </div>
);

// --- MAIN COMPONENT ---

export const SignInPage: React.FC<SignInPageProps> = ({
  title = <span className="font-light text-foreground tracking-tighter">Hoş Geldiniz</span>,
  description = "Hesabınıza giriş yapın ve devam edin",
  authMode = 'login',
  notice,
  heroImageSrc,
  testimonials = [],
  onSignIn,
  onGoogleSignIn,
  onGitHubSignIn,
  onToggleMode,
  oauthProviders,
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const hasOAuth = Boolean(oauthProviders?.google || oauthProviders?.github);

  return (
    <div className="h-[100dvh] flex flex-col md:flex-row font-geist w-[100dvw]">
      {/* Left column: sign-in form */}
      <section className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="flex flex-col gap-6">
            <h1 className="animate-element animate-delay-100 text-4xl md:text-5xl font-semibold leading-tight">{title}</h1>
            <p className="animate-element animate-delay-200 text-muted-foreground">{description}</p>
            {notice && (
              <div className="animate-element animate-delay-250 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                {notice}
              </div>
            )}

            <form className="space-y-5" onSubmit={onSignIn}>
              <div className="animate-element animate-delay-300">
                <label className="text-sm font-medium text-muted-foreground">Kullanıcı Adı</label>
                <GlassInputWrapper>
                  <input name="username" type="text" placeholder="Kullanıcı adınızı girin" className="w-full bg-transparent text-sm p-4 rounded-2xl focus:outline-none" />
                </GlassInputWrapper>
              </div>

              <div className="animate-element animate-delay-400">
                <label className="text-sm font-medium text-muted-foreground">Şifre</label>
                <GlassInputWrapper>
                  <div className="relative">
                    <input name="password" type={showPassword ? 'text' : 'password'} placeholder="Şifrenizi girin" className="w-full bg-transparent text-sm p-4 pr-12 rounded-2xl focus:outline-none" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute inset-y-0 right-3 flex items-center">
                      {showPassword ? <EyeOff className="w-5 h-5 text-muted-foreground hover:text-foreground transition-colors" /> : <Eye className="w-5 h-5 text-muted-foreground hover:text-foreground transition-colors" />}
                    </button>
                  </div>
                </GlassInputWrapper>
              </div>

              <div className="animate-element animate-delay-500 flex items-center text-sm">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" name="rememberMe" className="custom-checkbox" />
                  <span className="text-foreground/90">Beni hatırla</span>
                </label>
              </div>

              <button type="submit" className="animate-element animate-delay-600 w-full rounded-2xl bg-[#0a0a0a] border border-slate-800 py-4 font-bold text-slate-300 hover:text-white hover:border-violet-500/60 hover:bg-violet-500/10 hover:shadow-[0_0_25px_-5px_rgba(139,92,246,0.4)] transition-all duration-300 active:scale-[0.98]">
                {authMode === 'login' ? 'Giriş Yap' : 'Kayıt Ol'}
              </button>
            </form>

            {/* OAuth Divider + Buttons */}
            {hasOAuth && (
              <>
                <div className="animate-element animate-delay-650 flex items-center gap-3 my-2">
                  <div className="flex-1 h-px bg-slate-800" />
                  <span className="text-xs text-muted-foreground uppercase tracking-wider">veya</span>
                  <div className="flex-1 h-px bg-slate-800" />
                </div>

                <div className="animate-element animate-delay-700 flex gap-3">
                  {oauthProviders?.google && (
                    <button
                      type="button"
                      onClick={onGoogleSignIn}
                      className="flex-1 flex items-center justify-center gap-2.5 rounded-2xl bg-[#0a0a0a] border border-slate-800 py-3.5 text-sm font-medium text-slate-300 hover:text-white hover:border-slate-600 hover:bg-slate-900 transition-all duration-300 active:scale-[0.98]"
                    >
                      <GoogleIcon />
                      Google
                    </button>
                  )}
                  {oauthProviders?.github && (
                    <button
                      type="button"
                      onClick={onGitHubSignIn}
                      className="flex-1 flex items-center justify-center gap-2.5 rounded-2xl bg-[#0a0a0a] border border-slate-800 py-3.5 text-sm font-medium text-slate-300 hover:text-white hover:border-slate-600 hover:bg-slate-900 transition-all duration-300 active:scale-[0.98]"
                    >
                      <GitHubIcon />
                      GitHub
                    </button>
                  )}
                </div>
              </>
            )}

            <p className="animate-element animate-delay-700 text-center text-sm text-muted-foreground mt-4">
              {authMode === 'login' ? 'Hesabınız yok mu?' : 'Zaten hesabınız var mı?'} <a href="#" onClick={(e) => { e.preventDefault(); onToggleMode?.(); }} className="text-violet-400 hover:underline transition-colors font-medium">{authMode === 'login' ? 'Kayıt Ol' : 'Giriş Yap'}</a>
            </p>
          </div>
        </div>
      </section>

      {/* Right column: AI Architecture Animation */}
      <section className="hidden md:flex flex-1 relative p-4 items-center justify-center overflow-hidden bg-[#000000]">
        <div className="absolute inset-4 rounded-3xl bg-[#030712] border border-slate-800/50 overflow-hidden flex items-center justify-center shadow-2xl">
          {/* Abstract Grid Background */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#4f4f4f2e_1px,transparent_1px),linear-gradient(to_bottom,#4f4f4f2e_1px,transparent_1px)] bg-[size:3rem_3rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20"></div>
          
          {/* Animated Glow */}
          <motion.div 
            animate={{ scale: [1, 1.2, 1], opacity: [0.1, 0.3, 0.1] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
            className="absolute w-96 h-96 bg-blue-600/30 rounded-full blur-[100px]"
          />

          {/* Core Code Node */}
          <div className="relative z-10 flex items-center justify-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2, duration: 0.8, ease: "easeOut" }}
              className="relative"
            >
              {/* Central Hexagon or Container */}
              <div className="w-48 h-48 bg-slate-900 border border-slate-700 rounded-3xl flex items-center justify-center relative shadow-[0_0_40px_-10px_rgba(59,130,246,0.5)] z-20 overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-violet-500/10" />
                <Bot size={64} className="text-blue-500" />
              </div>

              {/* Orbiting Elements */}
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                className="absolute inset-[-60px] border border-blue-500/20 rounded-full border-dashed"
              >
                <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 p-3 bg-slate-900 border border-slate-700 rounded-xl text-blue-400">
                  <Code2 size={24} />
                </div>
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 p-3 bg-slate-900 border border-slate-700 rounded-xl text-violet-400">
                  <Sparkles size={24} />
                </div>
              </motion.div>

              <motion.div
                animate={{ rotate: -360 }}
                transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
                className="absolute inset-[-120px] border border-slate-700/50 rounded-full"
              >
                <div className="absolute top-1/2 left-0 -translate-x-1/2 -translate-y-1/2 p-3 bg-slate-900 border border-slate-700 rounded-full text-emerald-400">
                  <Cpu size={20} />
                </div>
              </motion.div>
            </motion.div>
          </div>
        </div>
      </section>
    </div>
  );
};  
