'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Clock, AlertCircle, TrendingUp, TrendingDown } from 'lucide-react';
import api from '@/lib/api';
import { Quote, OpportunityStage } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';

const stageColors: Record<OpportunityStage, string> = {
  [OpportunityStage.DISCOVERY]: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300',
  [OpportunityStage.CONCEPT]: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300',
  [OpportunityStage.QUOTE_SENT]: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-300',
  [OpportunityStage.FOLLOW_UP]: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300',
  [OpportunityStage.DECISION_PENDING]: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300',
  [OpportunityStage.WON]: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300',
  [OpportunityStage.LOST]: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300',
};

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function getDaysOverdue(dueDate: string | undefined): number | null {
  if (!dueDate) return null;
  const due = new Date(dueDate);
  const now = new Date();
  const diffMs = now.getTime() - due.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  return diffDays > 0 ? diffDays : null;
}

export default function OpportunitiesPage() {
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState<OpportunityStage | 'ALL'>('ALL');

  useEffect(() => {
    fetchOpportunities();
  }, [stageFilter]);

  const fetchOpportunities = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (stageFilter !== 'ALL') {
        params.stage = stageFilter;
      }

      const response = await api.get('/api/quotes/opportunities', { params });
      setOpportunities(response.data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load opportunities');
      }
    } finally {
      setLoading(false);
    }
  };

  const stages: (OpportunityStage | 'ALL')[] = ['ALL', ...Object.values(OpportunityStage)];

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-semibold mb-6">Opportunities</h1>
          
          {/* Stage Filter */}
          <div className="flex flex-wrap gap-2 mb-6">
            {stages.map((stage) => (
              <Button
                key={stage}
                variant={stageFilter === stage ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStageFilter(stage)}
              >
                {stage === 'ALL' ? 'All Stages' : stage.replace('_', ' ')}
              </Button>
            ))}
          </div>
        </div>

        {/* Opportunities List */}
        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        ) : opportunities.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">No opportunities found</div>
        ) : (
          <div className="grid gap-4">
            {opportunities.map((opp) => {
              const daysOverdue = getDaysOverdue(opp.next_action_due_date);
              const isOverdue = daysOverdue !== null && daysOverdue > 0;
              
              return (
                <Link key={opp.id} href={`/opportunities/${opp.id}`}>
                  <Card className={`hover:border-primary/50 transition-colors cursor-pointer ${isOverdue ? 'border-red-500' : ''}`}>
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="text-lg font-semibold">{opp.quote_number}</h3>
                            {opp.opportunity_stage && (
                              <Badge className={stageColors[opp.opportunity_stage]}>
                                {opp.opportunity_stage.replace('_', ' ')}
                              </Badge>
                            )}
                            {opp.close_probability !== undefined && (
                              <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                                {opp.close_probability}% probability
                              </Badge>
                            )}
                            {opp.total_amount > 0 && (
                              <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                                £{opp.total_amount.toLocaleString()}
                              </Badge>
                            )}
                            {isOverdue && (
                              <Badge variant="destructive" className="ml-2">
                                <AlertCircle className="h-3 w-3 mr-1" />
                                {daysOverdue}d overdue
                              </Badge>
                            )}
                          </div>
                          {opp.next_action && (
                            <div className="mb-2">
                              <span className="text-sm font-medium">Next Action: </span>
                              <span className="text-sm text-muted-foreground">{opp.next_action}</span>
                              {opp.next_action_due_date && (
                                <span className={`text-xs ml-2 ${isOverdue ? 'text-red-600 font-semibold' : 'text-muted-foreground'}`}>
                                  (Due: {new Date(opp.next_action_due_date).toLocaleDateString()})
                                </span>
                              )}
                            </div>
                          )}
                          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                            {opp.expected_close_date && (
                              <span className="flex items-center gap-1">
                                <TrendingUp className="h-3 w-3" />
                                Close: {new Date(opp.expected_close_date).toLocaleDateString()}
                              </span>
                            )}
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatTimeAgo(opp.updated_at)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
