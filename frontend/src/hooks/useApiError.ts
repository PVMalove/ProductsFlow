import { useState } from 'react';
import axios from 'axios';
import { UseFormSetError, FieldValues, Path } from 'react-hook-form';

export function useApiError<TFieldValues extends FieldValues>() {
  const [globalError, setGlobalError] = useState<string | null>(null);

  const handleApiError = (
    err: unknown,
    setError: UseFormSetError<TFieldValues>,
    defaultMessage: string = 'An unexpected error occurred'
  ) => {
    if (axios.isAxiosError(err) && err.response?.data?.error) {
      const errorData = err.response.data.error;
      if (errorData.details && Array.isArray(errorData.details)) {
        errorData.details.forEach((detail: { field?: string; issue: string }) => {
          if (detail.field) {
            setError(detail.field as Path<TFieldValues>, { type: 'server', message: detail.issue });
          } else {
            setGlobalError(detail.issue);
          }
        });
      } else {
        setGlobalError(errorData.message || defaultMessage);
      }
    } else {
      setGlobalError(defaultMessage);
    }
  };

  const clearGlobalError = () => setGlobalError(null);

  return { globalError, setGlobalError, clearGlobalError, handleApiError };
}
