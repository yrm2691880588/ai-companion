import type { FieldError as ErrorValue } from "react-hook-form";

export default function FieldError({ id, error }: { id: string; error?: ErrorValue }) {
  return error?.message ? <p id={id} className="danger-text" role="alert">{error.message}</p> : null;
}
