import React, { useState, useEffect } from 'react';
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
  X,
  KeyRound,
  Cpu,
  BarChart3,
} from 'lucide-react';
import { UserProfile } from '../../types/auth';
import { loginUser, registerUser, DEMO_USERS } from '../../services/auth';
import { isStandaloneMode, setStandaloneMode, onModeChange } from '../../config/mode';

interface AuthPageProps {
  onSuccess: (user: UserProfile) => void;
  onCancel?: () => void;
}

export const AuthPage: React.FC<AuthPageProps> = ({ onSuccess, onCancel }) => {
  const [standalone, setStandalone] = useState(() => isStandaloneMode());

  useEffect(() => {
    return onModeChange((s) => setStandalone(s));
  }, []);

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

  const getRoleIcon = (demo: (typeof DEMO_USERS)[0]) => {
    if (demo.role === 'client') {
      return <User className="size-4 text-emerald-600" />;
    }
    if (demo.lineCode === 'L1') {
      return <Headphones className="size-4 text-blue-600" />;
    }
    if (demo.lineCode === 'L2') {
      return <KeyRound className="size-4 text-indigo-600" />;
    }
    if (demo.lineCode === 'L3') {
      return <Cpu className="size-4 text-purple-600" />;
    }
    return <BarChart3 className="size-4 text-amber-600" />;
  };

  const getBadgeStyle = (demo: (typeof DEMO_USERS)[0]) => {
    if (demo.role === 'client') {
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    }
    if (demo.lineCode === 'L1') {
      return 'bg-blue-50 text-blue-700 border-blue-200';
    }
    if (demo.lineCode === 'L2') {
      return 'bg-indigo-50 text-indigo-700 border-indigo-200';
    }
    if (demo.lineCode === 'L3') {
      return 'bg-purple-50 text-purple-700 border-purple-200';
    }
    return 'bg-amber-50 text-amber-700 border-amber-200';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#f7f8f9] p-4 overflow-y-auto custom-scrollbar">
      <div className="relative w-full max-w-xl bg-white rounded-none border border-[#22242626] shadow-md p-6 sm:p-8 my-8">
        {/* Close / Back button */}
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            title="Вернуться к чату"
            className="absolute top-4 right-4 p-1.5 text-[#7f8792] hover:text-[#1a1a1a] hover:bg-[#f2f7fc] transition cursor-pointer"
          >
            <X className="size-5" />
          </button>
        )}

        {/* Logo & Header */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="size-12 rounded-none bg-[#db2b21] flex items-center justify-center text-white mb-3">
            <Sparkles className="size-6" />
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-[#1a1a1a] tracking-tight">
            Портал Поставщиков
          </h1>
          <p className="text-xs sm:text-sm text-[#7f8792] mt-1 font-semibold">
            Единая служба поддержки пользователей ЕАИСТ
          </p>
        </div>

        {/* Mode Switcher Banner */}
        <div
          className={`mb-5 p-2.5 rounded-none border text-xs flex items-center justify-between gap-3 ${
            standalone
              ? 'bg-[#eaf6ff] border-[#264b82]/30 text-[#264b82]'
              : 'bg-[#e7f8f2] border-[#0d9b68]/30 text-[#0d9b68]'
          }`}
        >
          <div className="flex items-center gap-2 min-w-0">
            <span
              className={`size-2 rounded-full shrink-0 ${
                standalone ? 'bg-[#264b82]' : 'bg-[#0d9b68]'
              }`}
            />
            <div className="truncate">
              <span className="font-bold block truncate text-[#1a1a1a]">
                {standalone ? 'Автономный режим (Демо)' : 'Режим связи с бэкендом (API)'}
              </span>
              <span className="text-[11px] text-[#7f8792] block truncate">
                {standalone
                  ? 'Автономная работа без обязательной БД'
                  : 'Запросы направляются к API серверу'}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setStandaloneMode(!standalone)}
            title={standalone ? 'Переключить на бэкенд' : 'Переключить в автономный режим'}
            className={`text-xs font-bold px-2.5 py-1 rounded-none transition cursor-pointer shrink-0 ${
              standalone
                ? 'bg-[#264b82] hover:bg-[#1c3f72] text-white'
                : 'bg-[#0d9b68] hover:bg-[#05895a] text-white'
            }`}
          >
            {standalone ? 'К API' : 'В Демо'}
          </button>
        </div>

        {/* Tabs: Вход / Регистрация */}
        <div className="flex p-0.5 bg-[#eeeeee] rounded-none border border-[#dddddd] mb-5">
          <button
            type="button"
            onClick={() => {
              setTab('login');
              setErrorMessage(null);
            }}
            className={`flex-1 py-2 text-xs sm:text-sm font-bold rounded-none transition cursor-pointer ${
              tab === 'login'
                ? 'bg-white text-[#1a1a1a] shadow-none border border-[#d4d4d5]'
                : 'text-[#7f8792] hover:text-[#1a1a1a]'
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
            className={`flex-1 py-2 text-xs sm:text-sm font-bold rounded-none transition cursor-pointer ${
              tab === 'register'
                ? 'bg-white text-[#1a1a1a] shadow-none border border-[#d4d4d5]'
                : 'text-[#7f8792] hover:text-[#1a1a1a]'
            }`}
          >
            Регистрация поставщика
          </button>
        </div>

        {/* Error message */}
        {errorMessage && (
          <div className="mb-4 p-3 rounded-none bg-[#fef0ef] border border-[#db2b21]/40 text-xs text-[#db2b21] leading-relaxed">
            {errorMessage}
          </div>
        )}

        {/* Login Form */}
        {tab === 'login' ? (
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-[#1a1a1a] mb-1">
                Электронная почта
              </label>
              <div className="relative">
                <Mail className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="supplier@example.com"
                  className="w-full text-xs sm:text-sm pl-9 pr-3 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] transition"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-bold text-[#1a1a1a]">
                  Пароль
                </label>
                <a
                  href="#forgot"
                  onClick={(e) => {
                    e.preventDefault();
                    alert('Для восстановления доступа обратитесь в службу поддержки через чат.');
                  }}
                  className="text-[11px] text-[#264b82] font-semibold hover:underline"
                >
                  Забыли пароль?
                </a>
              </div>
              <div className="relative">
                <Lock className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full text-xs sm:text-sm pl-9 pr-9 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7f8792] hover:text-[#1a1a1a] cursor-pointer"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 rounded-none bg-[#db2b21] hover:bg-[#cd1f15] active:bg-[#af221a] text-white font-bold text-xs sm:text-sm transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              <span>{isSubmitting ? 'Вход...' : 'Войти в личный кабинет'}</span>
              <ArrowRight className="size-4" />
            </button>
          </form>
        ) : (
          /* Register Form */
          <form onSubmit={handleRegister} className="space-y-3">
            <div>
              <label className="block text-xs font-bold text-[#1a1a1a] mb-1">
                Электронная почта *
              </label>
              <div className="relative">
                <Mail className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="company@example.com"
                  className="w-full text-xs sm:text-sm pl-9 pr-3 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#1a1a1a] mb-1">
                Пароль *
              </label>
              <div className="relative">
                <Lock className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Минимум 8 символов"
                  className="w-full text-xs sm:text-sm pl-9 pr-9 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7f8792] hover:text-[#1a1a1a] cursor-pointer"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div>
                <label className="block text-xs font-bold text-[#1a1a1a] mb-1">
                  ФИО представителя
                </label>
                <div className="relative">
                  <User className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Иванов И. И."
                    className="w-full text-xs pl-9 pr-3 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#1a1a1a] mb-1">
                  ИНН организации
                </label>
                <div className="relative">
                  <FileText className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    type="text"
                    value={inn}
                    maxLength={12}
                    onChange={(e) => setInn(e.target.value)}
                    placeholder="7701234567"
                    className="w-full text-xs pl-9 pr-3 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] font-mono transition"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#1a1a1a] mb-1">
                Наименование организации / ИП
              </label>
              <div className="relative">
                <Building2 className="size-4 text-[#7f8792] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="ООО «Поставка» или ИП Петров"
                  className="w-full text-xs sm:text-sm pl-9 pr-3 py-2 rounded-none border border-[#d4d4d5] focus:outline-none focus:border-[#264b82] transition"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 rounded-none bg-[#db2b21] hover:bg-[#cd1f15] active:bg-[#af221a] text-white font-bold text-xs sm:text-sm transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              <span>{isSubmitting ? 'Регистрация...' : 'Зарегистрироваться'}</span>
              <ArrowRight className="size-4" />
            </button>
          </form>
        )}

        {/* Quick Demo Login Section */}
        <div className="mt-5 pt-4 border-t border-[#e5e5e5]">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[#7f8792]">
              Быстрый вход для тестирования (5 профилей):
            </span>
            <span className="text-[10px] text-[#7f8792]">Вход в 1 клик</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {DEMO_USERS.map((demo, idx) => (
              <button
                key={demo.email}
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickDemoLogin(demo)}
                className={`flex items-start gap-2.5 p-2.5 rounded-none border border-[#22242626] hover:border-[#264b82] hover:bg-[#f2f7fc] text-left transition cursor-pointer group bg-white ${
                  idx === 4 ? 'sm:col-span-2' : ''
                }`}
              >
                <div className="size-8 rounded-none bg-[#f7f8f9] flex items-center justify-center shrink-0 border border-[#e5e5e5] mt-0.5 group-hover:border-[#264b82]/40">
                  {getRoleIcon(demo)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                    <span className="text-xs font-bold text-[#1a1a1a] group-hover:text-[#264b82]">
                      {demo.title}
                    </span>
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded-none border ${getBadgeStyle(
                        demo
                      )}`}
                    >
                      {demo.badge}
                    </span>
                  </div>
                  <p className="text-[11px] text-[#7f8792] line-clamp-1 leading-snug">
                    {demo.description}
                  </p>
                  <div className="text-[10px] text-[#999999] font-mono mt-0.5 truncate">
                    {demo.name} • {demo.email}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Security Badge Footer */}
        <div className="mt-4 text-center flex items-center justify-center gap-1.5 text-[11px] text-[#7f8792]">
          <ShieldCheck className="size-3.5 text-[#0d9b68]" />
          <span>Аутентификация по стандартам Правительства Москвы</span>
        </div>
      </div>
    </div>
  );
};
