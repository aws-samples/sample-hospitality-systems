import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';

export interface GuestInfoData {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  specialRequests: string;
}

interface GuestInfoFormProps {
  onSubmit: (data: GuestInfoData) => void;
  initialData?: Partial<GuestInfoData>;
  isLoading?: boolean;
}

interface FormErrors {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
}

const GuestInfoForm: React.FC<GuestInfoFormProps> = ({
  onSubmit,
  initialData,
  isLoading = false,
}) => {
  const { user } = useAuth();

  const [formData, setFormData] = useState<GuestInfoData>({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    specialRequests: '',
    ...initialData,
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  // Pre-fill from auth context if no initial data provided
  useEffect(() => {
    if (user && !initialData) {
      const nameParts = user.name.split(' ');
      setFormData((prev) => ({
        ...prev,
        firstName: prev.firstName || nameParts[0] || '',
        lastName: prev.lastName || nameParts.slice(1).join(' ') || '',
        email: prev.email || user.email || '',
      }));
    }
  }, [user, initialData]);

  const validate = (data: GuestInfoData): FormErrors => {
    const errs: FormErrors = {};
    if (!data.firstName.trim()) errs.firstName = 'First name is required';
    if (!data.lastName.trim()) errs.lastName = 'Last name is required';
    if (!data.email.trim()) {
      errs.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
      errs.email = 'Please enter a valid email address';
    }
    return errs;
  };

  const handleChange = (field: keyof GuestInfoData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (touched[field]) {
      const updated = { ...formData, [field]: value };
      setErrors(validate(updated));
    }
  };

  const handleBlur = (field: keyof GuestInfoData) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    setErrors(validate(formData));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const validationErrors = validate(formData);
    setErrors(validationErrors);
    setTouched({ firstName: true, lastName: true, email: true, phone: true });

    if (Object.keys(validationErrors).length === 0) {
      onSubmit(formData);
    }
  };

  const inputClass = (field: keyof FormErrors) =>
    `w-full rounded-lg border px-3 py-2.5 text-sm text-neutral-800 transition-colors focus:outline-none focus:ring-1 ${
      errors[field] && touched[field]
        ? 'border-red-400 focus:border-red-500 focus:ring-red-500'
        : 'border-neutral-300 focus:border-primary-600 focus:ring-primary-600'
    }`;

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <h2 className="font-display text-xl font-semibold text-neutral-900">Guest Information</h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* First Name */}
        <div>
          <label htmlFor="firstName" className="mb-1 block text-sm font-medium text-neutral-700">
            First Name <span className="text-red-500">*</span>
          </label>
          <input
            id="firstName"
            type="text"
            value={formData.firstName}
            onChange={(e) => handleChange('firstName', e.target.value)}
            onBlur={() => handleBlur('firstName')}
            className={inputClass('firstName')}
            placeholder="John"
          />
          {errors.firstName && touched.firstName && (
            <p className="mt-1 text-xs text-red-500">{errors.firstName}</p>
          )}
        </div>

        {/* Last Name */}
        <div>
          <label htmlFor="lastName" className="mb-1 block text-sm font-medium text-neutral-700">
            Last Name <span className="text-red-500">*</span>
          </label>
          <input
            id="lastName"
            type="text"
            value={formData.lastName}
            onChange={(e) => handleChange('lastName', e.target.value)}
            onBlur={() => handleBlur('lastName')}
            className={inputClass('lastName')}
            placeholder="Doe"
          />
          {errors.lastName && touched.lastName && (
            <p className="mt-1 text-xs text-red-500">{errors.lastName}</p>
          )}
        </div>
      </div>

      {/* Email */}
      <div>
        <label htmlFor="email" className="mb-1 block text-sm font-medium text-neutral-700">
          Email Address <span className="text-red-500">*</span>
        </label>
        <input
          id="email"
          type="email"
          value={formData.email}
          onChange={(e) => handleChange('email', e.target.value)}
          onBlur={() => handleBlur('email')}
          className={inputClass('email')}
          placeholder="john.doe@example.com"
        />
        {errors.email && touched.email && (
          <p className="mt-1 text-xs text-red-500">{errors.email}</p>
        )}
      </div>

      {/* Phone */}
      <div>
        <label htmlFor="phone" className="mb-1 block text-sm font-medium text-neutral-700">
          Phone Number
        </label>
        <input
          id="phone"
          type="tel"
          value={formData.phone}
          onChange={(e) => handleChange('phone', e.target.value)}
          onBlur={() => handleBlur('phone')}
          className={inputClass('phone')}
          placeholder="+1 (555) 000-0000"
        />
      </div>

      {/* Special Requests */}
      <div>
        <label htmlFor="specialRequests" className="mb-1 block text-sm font-medium text-neutral-700">
          Special Requests
        </label>
        <textarea
          id="specialRequests"
          value={formData.specialRequests}
          onChange={(e) => handleChange('specialRequests', e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-neutral-300 px-3 py-2.5 text-sm text-neutral-800 transition-colors focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 resize-none"
          placeholder="e.g., Late check-in, extra pillows, high floor preference..."
        />
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={isLoading}
        className="w-full rounded-lg bg-primary-600 py-3 text-sm font-semibold text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-600/40 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
      >
        {isLoading ? 'Saving...' : 'Continue to Review'}
      </button>
    </form>
  );
};

export default GuestInfoForm;
