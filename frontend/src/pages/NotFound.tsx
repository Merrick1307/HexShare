import { Link } from 'react-router-dom';
import { FileQuestion } from 'lucide-react';
import { Button } from '../components/ui/Button';

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-4 text-center">
      <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-zinc-100">
        <FileQuestion className="h-10 w-10 text-zinc-400" />
      </div>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight text-zinc-950">Page not found</h1>
      <p className="mt-3 max-w-md text-sm text-zinc-500">
        The page you are looking for does not exist or has been moved.
      </p>
      <Link to="/" className="mt-8">
        <Button variant="primary">Back to home</Button>
      </Link>
    </div>
  );
}
