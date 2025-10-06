import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import {
  Search,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileText,
  Download,
  RefreshCw,
  Calendar,
  Hash,
  MessageSquare,
  Globe,
  FileSearch
} from 'lucide-react';

const RequestStatus = () => {
  const [requests, setRequests] = useState([]);
  const [searchId, setSearchId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  // Sample data - in real app this would come from your API
  useEffect(() => {
    const sampleRequests = [
      {
        id: 'req_1703123456_abc123',
        type: 'Human Review',
        query: 'Please review this research document for accuracy and provide recommendations.',
        status: 'pending_review',
        submittedAt: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
        estimatedCompletion: new Date(Date.now() + 4 * 60 * 60 * 1000), // 4 hours from now
        priority: 'high',
        documentName: 'research-report.pdf'
      },
      {
        id: 'req_1703123400_def456',
        type: 'Search Agent',
        query: 'Latest developments in AI and machine learning 2024',
        status: 'completed',
        submittedAt: new Date(Date.now() - 5 * 60 * 60 * 1000), // 5 hours ago
        completedAt: new Date(Date.now() - 4.5 * 60 * 60 * 1000), // 4.5 hours ago
        result: 'Search completed with 15 relevant sources found and summarized.',
        downloadUrl: 'https://example.com/reports/search-summary.pdf'
      },
      {
        id: 'req_1703123300_ghi789',
        type: 'Document Querier',
        query: 'What are the main conclusions from this research paper?',
        status: 'processing',
        submittedAt: new Date(Date.now() - 30 * 60 * 1000), // 30 minutes ago
        estimatedCompletion: new Date(Date.now() + 10 * 60 * 1000), // 10 minutes from now
        documentName: 'research-paper.pdf',
        progress: 75
      },
      {
        id: 'req_1703123200_jkl012',
        type: 'PDF Generator',
        query: 'Convert HTML report to PDF format',
        status: 'completed',
        submittedAt: new Date(Date.now() - 1 * 60 * 60 * 1000), // 1 hour ago
        completedAt: new Date(Date.now() - 45 * 60 * 1000), // 45 minutes ago
        result: 'PDF generated successfully and stored in S3.',
        downloadUrl: 'https://example.com/reports/generated-report.pdf'
      },
      {
        id: 'req_1703123100_mno345',
        type: 'Human Review',
        query: 'Review contract terms and conditions for legal compliance.',
        status: 'rejected',
        submittedAt: new Date(Date.now() - 8 * 60 * 60 * 1000), // 8 hours ago
        completedAt: new Date(Date.now() - 6 * 60 * 60 * 1000), // 6 hours ago
        reviewerComments: 'Document contains insufficient information for proper legal review. Please provide complete contract with all appendices.',
        documentName: 'contract-draft.pdf'
      }
    ];
    setRequests(sampleRequests);
  }, []);

  const handleSearch = () => {
    if (!searchId.trim()) {
      toast({
        title: "Error",
        description: "Please enter a request ID to search.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    // Simulate API call
    setTimeout(() => {
      const found = requests.find(req => req.id.includes(searchId));
      if (found) {
        toast({
          title: "Request Found",
          description: `Found request: ${found.type}`,
        });
        // Scroll to the request or highlight it
      } else {
        toast({
          title: "Not Found",
          description: "No request found with that ID.",
          variant: "destructive",
        });
      }
      setIsLoading(false);
    }, 1000);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case 'processing':
        return <Clock className="h-4 w-4 text-blue-600" />;
      case 'pending_review':
        return <AlertTriangle className="h-4 w-4 text-yellow-600" />;
      case 'rejected':
        return <XCircle className="h-4 w-4 text-red-600" />;
      default:
        return <Clock className="h-4 w-4" />;
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'completed':
        return 'secondary';
      case 'processing':
        return 'default';
      case 'pending_review':
        return 'destructive';
      case 'rejected':
        return 'destructive';
      default:
        return 'outline';
    }
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'Search Agent':
        return <Globe className="h-4 w-4" />;
      case 'Document Querier':
        return <FileSearch className="h-4 w-4" />;
      case 'PDF Generator':
        return <FileText className="h-4 w-4" />;
      case 'Human Review':
        return <MessageSquare className="h-4 w-4" />;
      default:
        return <FileText className="h-4 w-4" />;
    }
  };

  const formatStatus = (status) => {
    switch (status) {
      case 'pending_review':
        return 'Pending Review';
      case 'processing':
        return 'Processing';
      case 'completed':
        return 'Completed';
      case 'rejected':
        return 'Rejected';
      default:
        return status;
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Request Status</h1>
        <p className="text-muted-foreground">
          Track the progress of your AI agent requests and human review submissions
        </p>
      </div>

      {/* Search */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Search className="h-5 w-5" />
            <span>Search Request</span>
          </CardTitle>
          <CardDescription>
            Enter a request ID to quickly find and track a specific request
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex space-x-2">
            <div className="flex-1">
              <Label htmlFor="search-id" className="sr-only">Request ID</Label>
              <Input
                id="search-id"
                placeholder="Enter request ID (e.g., req_1703123456_abc123)"
                value={searchId}
                onChange={(e) => setSearchId(e.target.value)}
              />
            </div>
            <Button onClick={handleSearch} disabled={isLoading}>
              {isLoading ? (
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              Search
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Requests List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Your Requests</h2>
          <Badge variant="outline">{requests.length} total</Badge>
        </div>

        {requests.map((request) => (
          <Card key={request.id}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="space-y-2">
                  <div className="flex items-center space-x-3">
                    {getTypeIcon(request.type)}
                    <h3 className="font-semibold">{request.type}</h3>
                    <Badge variant={getStatusVariant(request.status)} className="flex items-center space-x-1">
                      {getStatusIcon(request.status)}
                      <span>{formatStatus(request.status)}</span>
                    </Badge>
                    {request.priority && (
                      <Badge variant={request.priority === 'high' ? 'destructive' : 'secondary'}>
                        {request.priority} priority
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center space-x-1 text-sm text-muted-foreground">
                    <Hash className="h-3 w-3" />
                    <span className="font-mono">{request.id}</span>
                  </div>
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  <div className="flex items-center space-x-1">
                    <Calendar className="h-3 w-3" />
                    <span>Submitted {request.submittedAt.toLocaleString()}</span>
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Query */}
              <div>
                <h4 className="font-medium mb-1">Request</h4>
                <p className="text-sm text-muted-foreground">{request.query}</p>
              </div>

              {/* Document */}
              {request.documentName && (
                <div>
                  <h4 className="font-medium mb-1">Document</h4>
                  <div className="flex items-center space-x-2">
                    <FileText className="h-4 w-4" />
                    <span className="text-sm">{request.documentName}</span>
                  </div>
                </div>
              )}

              <Separator />

              {/* Status Details */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Processing Status */}
                {request.status === 'processing' && (
                  <div>
                    <h4 className="font-medium mb-2">Progress</h4>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Processing...</span>
                        <span>{request.progress}%</span>
                      </div>
                      <div className="w-full bg-secondary rounded-full h-2">
                        <div 
                          className="bg-primary h-2 rounded-full transition-all duration-300" 
                          style={{ width: `${request.progress}%` }}
                        />
                      </div>
                      {request.estimatedCompletion && (
                        <p className="text-xs text-muted-foreground">
                          Est. completion: {request.estimatedCompletion.toLocaleString()}
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Pending Review */}
                {request.status === 'pending_review' && (
                  <div>
                    <h4 className="font-medium mb-2">Review Status</h4>
                    <p className="text-sm text-muted-foreground">
                      Your request is in the human review queue. 
                      {request.estimatedCompletion && (
                        <> Expected completion: {request.estimatedCompletion.toLocaleString()}</>
                      )}
                    </p>
                  </div>
                )}

                {/* Completed */}
                {request.status === 'completed' && (
                  <div>
                    <h4 className="font-medium mb-2">Result</h4>
                    <p className="text-sm text-muted-foreground mb-2">{request.result}</p>
                    {request.downloadUrl && (
                      <Button variant="outline" size="sm">
                        <Download className="mr-2 h-4 w-4" />
                        Download Result
                      </Button>
                    )}
                    <p className="text-xs text-muted-foreground mt-2">
                      Completed: {request.completedAt.toLocaleString()}
                    </p>
                  </div>
                )}

                {/* Rejected */}
                {request.status === 'rejected' && (
                  <div>
                    <h4 className="font-medium mb-2">Reviewer Comments</h4>
                    <p className="text-sm text-muted-foreground">{request.reviewerComments}</p>
                    <p className="text-xs text-muted-foreground mt-2">
                      Reviewed: {request.completedAt.toLocaleString()}
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Toaster />
    </div>
  );
};

export default RequestStatus;
