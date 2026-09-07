/**
 * File picker and upload state for the Check surface.
 */

export interface ContractUploadProps {
  onUpload: (file: File) => void;
  pending: boolean;
  error?: string;
}

export function ContractUpload({ onUpload, pending, error }: ContractUploadProps) {
  throw new Error("Not implemented");
}

// TODO:
//  1. Accept only the configured MIME types and show the size limit before upload.
//  2. Client-side validation is a convenience; the backend still validates and is authoritative.
//  3. Show a progress state -- clause-by-clause review takes many LLM calls.
