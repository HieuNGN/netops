import { Link } from 'react-router-dom';
import { Home, ArrowLeft } from 'lucide-react';

export function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f4f4f4] dark:bg-[#161616] px-4">
      <div className="max-w-md w-full text-center">
        <h1 className="text-9xl font-bold text-[#161616] dark:text-[#a8a8a8]">404</h1>
        <h2 className="mt-4 text-2xl font-bold text-[#161616] dark:text-white">
          Page Not Found
        </h2>
        <p className="mt-2 text-[#525252] dark:text-[#a8a8a8]">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-8 flex items-center justify-center space-x-4">
          <Link
            to="/"
            className="flex items-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] transition-colors"
          >
            <Home className="h-4 w-4" />
            <span>Go Home</span>
          </Link>
          <button
            onClick={() => window.history.back()}
            className="flex items-center space-x-2 px-4 py-2 bg-[#e0e0e0] dark:bg-[#262626] text-[#161616] dark:text-white rounded-sm hover:bg-[#c6c6c6] dark:hover:bg-[#393939] transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Go Back</span>
          </button>
        </div>
      </div>
    </div>
  );
}
