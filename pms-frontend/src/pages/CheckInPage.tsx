import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Card, PageHeader } from '../components/ui';

export default function CheckInPage() {
  return (
    <div data-testid="checkin-page">
      <PageHeader title="Check-In" />
      <Card padding="md">
        <p className="text-sm text-neutral-600">
          Use the{' '}
          <Link
            to="/stays"
            className="inline-flex items-center gap-1 font-medium text-primary-600 hover:text-primary-700 transition-colors"
          >
            Stays page
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>{' '}
          to check in guests — click the <span className="font-medium text-neutral-900">Check In</span> button on
          any CONFIRMED reservation.
        </p>
      </Card>
    </div>
  );
}
