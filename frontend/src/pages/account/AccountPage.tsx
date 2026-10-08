import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../context/AuthContext';
import * as guestService from '../../services/guestService';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import PublicLayout from '../../components/layout/PublicLayout';

const AccountPage: React.FC = () => {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [editing, setEditing] = useState(false);
  const [editFirstName, setEditFirstName] = useState('');
  const [editLastName, setEditLastName] = useState('');
  const [editPhone, setEditPhone] = useState('');

  // Redirect if not authenticated
  if (!isAuthenticated) {
    navigate('/signin?returnUrl=/account');
    return null;
  }

  const { data: guest, isLoading } = useQuery({
    queryKey: ['guest', user?.guestId],
    queryFn: () => guestService.getGuest(user!.guestId),
    enabled: !!user?.guestId,
  });

  const updateMutation = useMutation({
    mutationFn: (data: guestService.UpdateGuestData) =>
      guestService.updateGuest(user!.guestId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['guest', user?.guestId] });
      setEditing(false);
    },
  });

  const handleStartEdit = () => {
    if (guest) {
      setEditFirstName(guest.firstName);
      setEditLastName(guest.lastName);
      setEditPhone(guest.phone || '');
    }
    setEditing(true);
  };

  const handleSaveEdit = () => {
    updateMutation.mutate({
      firstName: editFirstName,
      lastName: editLastName,
      phone: editPhone,
    });
  };

  const handleCancelEdit = () => {
    setEditing(false);
  };

  const inputClass =
    'w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-800 ' +
    'focus:border-primary-600 focus:outline-hidden focus:ring-1 focus:ring-primary-600 transition-colors';

  return (
    <PublicLayout>
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        {/* Welcome */}
        <h1 className="font-display text-3xl font-bold text-neutral-900">
          Welcome{guest ? `, ${guest.firstName}` : user ? `, ${user.name}` : ''}
        </h1>
        <p className="mt-1 text-neutral-600">Manage your profile and reservations</p>

        {isLoading ? (
          <div className="mt-10 flex justify-center">
            <LoadingSpinner message="Loading profile..." />
          </div>
        ) : (
          <>
            {/* Profile info card */}
            <div className="mt-8 rounded-xl border border-neutral-200 bg-white p-6 shadow-xs">
              <div className="flex items-center justify-between">
                <h2 className="font-display text-lg font-semibold text-neutral-900">
                  Profile Information
                </h2>
                {!editing && (
                  <button
                    type="button"
                    onClick={handleStartEdit}
                    className="text-sm font-medium text-primary-600 hover:text-primary-700"
                  >
                    Edit Profile
                  </button>
                )}
              </div>

              {editing ? (
                /* Edit form */
                <div className="mt-5 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="mb-1 block text-sm font-medium text-neutral-700">
                        First Name
                      </label>
                      <input
                        type="text"
                        value={editFirstName}
                        onChange={(e) => setEditFirstName(e.target.value)}
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-sm font-medium text-neutral-700">
                        Last Name
                      </label>
                      <input
                        type="text"
                        value={editLastName}
                        onChange={(e) => setEditLastName(e.target.value)}
                        className={inputClass}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-neutral-700">
                      Email
                    </label>
                    <input
                      type="email"
                      value={user?.email ?? ''}
                      disabled
                      className={`${inputClass} bg-neutral-50 text-neutral-400 cursor-not-allowed`}
                    />
                    <p className="mt-1 text-xs text-neutral-400">
                      Email cannot be changed here
                    </p>
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-neutral-700">
                      Phone
                    </label>
                    <input
                      type="tel"
                      value={editPhone}
                      onChange={(e) => setEditPhone(e.target.value)}
                      className={inputClass}
                      placeholder="+1 (555) 000-0000"
                    />
                  </div>

                  {updateMutation.isError && (
                    <p className="text-sm text-red-500">Failed to update profile. Please try again.</p>
                  )}

                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={handleSaveEdit}
                      disabled={updateMutation.isPending}
                      className="rounded-lg bg-primary-600 px-5 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60 transition-colors"
                    >
                      {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelEdit}
                      className="rounded-lg border border-neutral-300 px-5 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                /* Display profile */
                <div className="mt-5 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs font-medium text-neutral-500">Name</p>
                      <p className="mt-0.5 text-sm font-medium text-neutral-800">
                        {guest
                          ? `${guest.firstName} ${guest.lastName}`
                          : user?.name ?? 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-neutral-500">Email</p>
                      <p className="mt-0.5 text-sm font-medium text-neutral-800">
                        {guest?.email ?? user?.email ?? 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-neutral-500">Phone</p>
                      <p className="mt-0.5 text-sm font-medium text-neutral-800">
                        {guest?.phone || 'Not provided'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Quick links */}
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <Link
                to="/account/reservations"
                className="flex items-center gap-4 rounded-xl border border-neutral-200 bg-white p-5 shadow-xs hover:border-primary-300 hover:shadow-md transition-all"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary-50">
                  <svg className="h-6 w-6 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-neutral-800">My Reservations</h3>
                  <p className="text-xs text-neutral-500">View and manage your bookings</p>
                </div>
              </Link>

              <Link
                to="/"
                className="flex items-center gap-4 rounded-xl border border-neutral-200 bg-white p-5 shadow-xs hover:border-primary-300 hover:shadow-md transition-all"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent-50">
                  <svg className="h-6 w-6 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-neutral-800">Book a Stay</h3>
                  <p className="text-xs text-neutral-500">Search for your next destination</p>
                </div>
              </Link>
            </div>
          </>
        )}
      </div>
    </PublicLayout>
  );
};

export default AccountPage;
