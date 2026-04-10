"use client";

import { useCallback } from "react";
import { Upload, FileText } from "lucide-react";

interface UploadSectionProps {
  onFileUpload: (file: File) => void;
  loading: boolean;
  error: string | null;
}

export function UploadSection({
  onFileUpload,
  loading,
  error,
}: UploadSectionProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file && (file.name.endsWith(".pdf") || file.name.endsWith(".docx"))) {
        onFileUpload(file);
      }
    },
    [onFileUpload]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileUpload(file);
      }
    },
    [onFileUpload]
  );

  return (
    <div className="glass rounded-2xl p-12 text-center">
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        className="border-2 border-dashed border-slate-600 rounded-xl p-16 hover:border-blue-500 transition-colors"
      >
        {loading ? (
          <div className="space-y-4">
            <div className="animate-spin h-16 w-16 border-4 border-blue-500 border-t-transparent rounded-full mx-auto" />
            <p className="text-slate-400">Analyzing document...</p>
          </div>
        ) : (
          <>
            <Upload className="h-16 w-16 text-slate-400 mx-auto mb-4" />
            <h2 className="text-2xl font-semibold text-white mb-2">
              Upload DAT Document
            </h2>
            <p className="text-slate-400 mb-6">
              Drag and drop your Document d&apos;Architecture Technique (.pdf or
              .docx)
            </p>
            <label className="inline-block">
              <input
                type="file"
                accept=".pdf,.docx"
                onChange={handleFileInput}
                className="hidden"
              />
              <span className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg cursor-pointer transition-colors">
                <FileText className="h-5 w-5" />
                Select File
              </span>
            </label>
          </>
        )}
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-900/20 border border-red-500/50 rounded-lg">
          <p className="text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
}
