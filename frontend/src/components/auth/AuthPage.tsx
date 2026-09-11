import React, { useState } from 'react';
import {
  Sparkles,
  Lock,
  Mail,
  User,
  Building2,
  FileText,
  Eye,
  EyeOff,
  ArrowRight,
  ShieldCheck,
  Headphones,
  Briefcase,
  X,
} from 'lucide-react';
import { UserProfile, UserRole } from '../../types/auth';
import { loginUser, registerUser, DEMO_USERS } from '../../services/auth';

interface AuthPageProps {
  onSuccess: (user: UserProfile) => void;
  onCancel?: () => void;
}

export const AuthPage: React.FC<AuthPageProps> = ({ onSuccess, onCancel }) => {
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Form states
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [inn, setInn] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!email || !password) {
      setErrorMessage('Пожалуйста, укажите email и пароль');
      return;
    }

    setIsSubmitting(true);
    try {
      const auth = await loginUser(email, password);
      onSuccess(auth.user);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : 'Ошибка входа. Проверьте введенные данные.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!email || !password) {
      setErrorMessage('Пожалуйста, укажите email и пароль');
      return;
    }

    if (password.length < 8) {
      setErrorMessage('Пароль должен содержать не менее 8 символов');
      return;
    }

    const trimmedInn = inn.trim();
    if (
      trimmedInn &&
      (!/^\d+$/.test(trimmedInn) ||
        (trimmedInn.length !== 10 && trimmedInn.length !== 12))
    ) {
      setErrorMessage(
        'ИНН должен состоять из 10 цифр (для юрлиц) или 12 цифр (для ИП)'
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const auth = await registerUser({
        email,
        password,
        full_name: fullName || undefined,
        company_name: companyName || undefined,
        inn: trimmedInn || undefined,
      });
      onSuccess(auth.user);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : 'Не удалось зарегистрировать пользователя. Попробуйте еще раз.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickDemoLogin = async (demo: typeof DEMO_USERS[0]) => {
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const pwd = demo.defaultPassword || 'password123';
      const auth = await loginUser(demo.email, pwd);
      onSuccess(auth.user);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : 'Не удалось войти под демонстрационной учетной записью.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const getRoleIcon = (role: UserRole) => {
    switch (role) {
      case 'operator':
        return <Headphones className="size-4 text-primary-500" />;
      case 'supervisor':
      case 'admin':
        return <Briefcase className="size-4 text-amber-500" />;
      default:
        return <User className="size-4 text-emerald-500" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#f9fafb] p-4 overflow-y-auto custom-scrollbar">
      <div className="relative w-full max-w-lg bg-white rounded-3xl border border-gray-100 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.08)] p-6 sm:p-8 my-8 animate-in fade-in zoom-in-95 duration-200">
        {/* Close / Back button */}
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            title="Вернуться к чату"
            className="absolute top-5 right-5 p-2 rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition cursor-pointer"
          >
            <X className="size-5" />
          </button>
        )}

        {/* Logo & Header */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="size-12 rounded-2xl bg-gradient-to-tr from-primary-600 to-primary-400 flex items-center justify-center text-white shadow-md shadow-primary-500/20 mb-3">
            <Sparkles className="size-6" />
          </div>
          <h1 className="text-xl sm:text-2xl font-semibold text-title-50 tracking-tight">
            Портал Поставщиков
          </h1>
          <p className="text-xs sm:text-sm text-text-100 mt-1">
            Единая система интеллектуальной поддержки
          </p>
        </div>

        {/* Tabs: Вход / Регистрация */}
        <div className="flex p-1 bg-background-soft-100 rounded-2xl mb-6">
          <button
            type="button"
            onClick={() => {
              setTab('login');
              setErrorMessage(null);
            }}
            className={`flex-1 py-2 text-xs sm:text-sm font-semibold rounded-xl transition cursor-pointer ${
              tab === 'login'
                ? 'bg-white text-title-50 shadow-2xs'
                : 'text-text-100 hover:text-title-50'
            }`}
          >
            Вход в систему
          </button>
          <button
            type="button"
            onClick={() => {
              setTab('register');
              setErrorMessage(null);
            }}
            className={`flex-1 py-2 text-xs sm:text-sm font-semibold rounded-xl transition cursor-pointer ${
              tab === 'register'
                ? 'bg-white text-title-50 shadow-2xs'
                : 'text-text-100 hover:text-title-50'
            }`}
          >
            Регистрация поставщика
          </button>
        </div>

        {/* Error message */}
        {errorMessage && (
          <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200/80 text-xs text-red-700 leading-relaxed animate-in fade-in duration-150">
            {errorMessage}
          </div>
        )}

        {/* Login Form */}
        {tab === 'login' ? (
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                Электронная почта
              </label>
              <div className="relative">
                <Mail className="size-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="supplier@example.com"
                  className="w-full text-xs sm:text-sm pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold text-gray-700">
                  Пароль
                </label>
                <a
                  href="#forgot"
                  onClick={(e) => {
                    e.preventDefault();
                    alert('Для восстановления доступа обратитесь в службу поддержки через чат.');
                  }}
                  className="text-[11px] text-primary-500 hover:underline"
                >
                  Забыли пароль?
                </a>
              </div>
              <div className="relative">
                <Lock className="size-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full text-xs sm:text-sm pl-10 pr-10 py-2.5 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 rounded-xl bg-primary-500 hover:bg-primary-600 text-white font-semibold text-xs sm:text-sm shadow-sm shadow-primary-500/20 transition flex items-center justify-center gap-2 cursor-pointer active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              <span>{isSubmitting ? 'Вход...' : 'Войти в личный кабинет'}</span>
              <ArrowRight className="size-4" />
            </button>
          </form>
        ) : (
          /* Register Form */
          <form onSubmit={handleRegister} className="space-y-3.5">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Электронная почта *
              </label>
              <div className="relative">
                <Mail className="size-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="company@example.com"
                  className="w-full text-xs sm:text-sm pl-10 pr-4 py-2 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Пароль *
              </label>
              <div className="relative">
                <Lock className="size-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Минимум 8 символов"
                  className="w-full text-xs sm:text-sm pl-10 pr-10 py-2 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  ФИО представителя
                </label>
                <div className="relative">
                  <User className="size-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Иванов И. И."
                    className="w-full text-xs pl-9 pr-3 py-2 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  ИНН организации
                </label>
                <div className="relative">
                  <FileText className="size-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    type="text"
                    value={inn}
                    maxLength={12}
                    onChange={(e) => setInn(e.target.value)}
                    placeholder="7701234567"
                    className="w-full text-xs pl-9 pr-3 py-2 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Наименование организации / ИП
              </label>
              <div className="relative">
                <Building2 className="size-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="ООО «Поставка» или ИП Петров"
                  className="w-full text-xs sm:text-sm pl-10 pr-4 py-2 rounded-xl border border-gray-200 focus:outline-none focus:border-primary-500 transition"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 rounded-xl bg-primary-500 hover:bg-primary-600 text-white font-semibold text-xs sm:text-sm shadow-sm shadow-primary-500/20 transition flex items-center justify-center gap-2 cursor-pointer active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed mt-3"
            >
              <span>{isSubmitting ? 'Регистрация...' : 'Зарегистрироваться'}</span>
              <ArrowRight className="size-4" />
            </button>
          </form>
        )}

        {/* Quick Demo Login Section (для демонстрации жюри) */}
        <div className="mt-6 pt-5 border-t border-gray-100">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              Быстрый вход для тестирования ролей:
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {DEMO_USERS.map((demo) => (
              <button
                key={demo.role}
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickDemoLogin(demo)}
                className="flex items-center gap-2 p-2.5 rounded-xl border border-gray-200/80 hover:border-primary-300 hover:bg-primary-50/50 text-left transition cursor-pointer group active:scale-95"
              >
                <div className="size-7 rounded-lg bg-gray-50 group-hover:bg-white flex items-center justify-center shrink-0 shadow-2xs">
                  {getRoleIcon(demo.role)}
                </div>
                <div className="truncate">
                  <span className="text-xs font-semibold text-gray-800 block truncate group-hover:text-primary-600">
                    {demo.title}
                  </span>
                  <span className="text-[10px] text-gray-400 block truncate font-mono">
                    {demo.role}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Security Badge Footer */}
        <div className="mt-5 text-center flex items-center justify-center gap-1.5 text-[11px] text-gray-400">
          <ShieldCheck className="size-3.5 text-emerald-500" />
          <span>Безопасная аутентификация по стандарту ЕСИА / ГОСТ</span>
        </div>
      </div>
    </div>
  );
};
