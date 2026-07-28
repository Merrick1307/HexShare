import {
  File,
  FileArchive,
  FileImage,
  FileSpreadsheet,
  FileText,
  Presentation,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../lib/utils';

type FileTypeStyle = {
  label: string;
  name: string;
  icon: LucideIcon;
  className: string;
};

function extensionFor(fileName: string): string {
  const lastDot = fileName.lastIndexOf('.');
  return lastDot >= 0 ? fileName.slice(lastDot + 1).toLowerCase() : '';
}

function styleFor(fileName: string, mimeType?: string | null): FileTypeStyle {
  const extension = extensionFor(fileName);
  const mime = (mimeType || '').toLowerCase();

  if (extension === 'pdf' || mime === 'application/pdf') {
    return { label: 'PDF', name: 'PDF', icon: FileText, className: 'bg-red-600' };
  }
  if (['doc', 'docx'].includes(extension) || mime.includes('word')) {
    return { label: 'DOC', name: 'Word document', icon: FileText, className: 'bg-blue-600' };
  }
  if (
    ['xls', 'xlsx', 'csv'].includes(extension)
    || mime.includes('spreadsheet')
    || mime.includes('excel')
    || mime === 'text/csv'
  ) {
    return {
      label: extension === 'csv' ? 'CSV' : 'XLS',
      name: extension === 'csv' ? 'CSV' : 'Spreadsheet',
      icon: FileSpreadsheet,
      className: 'bg-emerald-600',
    };
  }
  if (['ppt', 'pptx'].includes(extension) || mime.includes('presentation') || mime.includes('powerpoint')) {
    return { label: 'PPT', name: 'Presentation', icon: Presentation, className: 'bg-orange-600' };
  }
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'].includes(extension) || mime.startsWith('image/')) {
    return { label: 'IMG', name: 'Image', icon: FileImage, className: 'bg-violet-600' };
  }
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension) || mime.includes('zip') || mime.includes('archive')) {
    return { label: 'ZIP', name: 'Archive', icon: FileArchive, className: 'bg-amber-600' };
  }
  if (['txt', 'md', 'rtf'].includes(extension) || mime.startsWith('text/')) {
    return {
      label: extension === 'md' ? 'MD' : 'TXT',
      name: extension === 'md' ? 'Markdown' : 'Text document',
      icon: FileText,
      className: 'bg-slate-600',
    };
  }

  return {
    label: extension ? extension.slice(0, 3).toUpperCase() : 'FILE',
    name: extension ? `${extension.toUpperCase()} file` : 'File',
    icon: File,
    className: 'bg-zinc-600',
  };
}

export function FileTypeIcon({
  fileName,
  mimeType,
  size = 'md',
  className,
}: {
  fileName: string;
  mimeType?: string | null;
  size?: 'sm' | 'md';
  className?: string;
}) {
  const style = styleFor(fileName, mimeType);
  const Icon = style.icon;

  return (
    <div
      role="img"
      aria-label={`${style.name} file`}
      title={style.name}
      className={cn(
        'relative flex shrink-0 flex-col items-center justify-center gap-0.5 overflow-hidden rounded-md text-white shadow-sm ring-1 ring-black/5',
        size === 'sm' ? 'h-8 w-8' : 'h-10 w-10',
        style.className,
        className,
      )}
    >
      <span className="absolute right-0 top-0 h-2.5 w-2.5 rounded-bl bg-white/25" />
      <Icon className={size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} aria-hidden="true" />
      <span className={cn('font-bold uppercase leading-none tracking-wide', size === 'sm' ? 'text-[7px]' : 'text-[8px]')}>
        {style.label}
      </span>
    </div>
  );
}
