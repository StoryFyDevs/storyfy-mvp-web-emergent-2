import { NhostClient } from '@nhost/nhost-js';

const nhost = new NhostClient({
  subdomain: process.env.REACT_APP_NHOST_SUBDOMAIN || 'placeholder',
  region: process.env.REACT_APP_NHOST_REGION || 'us-east-1',
});

export default nhost;
