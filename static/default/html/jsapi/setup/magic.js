var SetupMagic = {
  gmail: {
    address: [
      "@gmail.com",
      "@googlemail.com"
    ],
    sources: {
      name: 'Gmail Source',
      host: 'imap.gmail.com',
      port: 993,
      protocol: 'imap_ssl'
    },
    sending: {
      name: 'Gmail Sending',
      host: 'smtp.gmail.com',
      port: 587,
      protocol: 'smtp'
    }
  },
  outlook: {
    address: [
      "@hotmail.com",
      "@outlook.com"
    ],
    sources: {
      name: 'Outlook Source',
      host: 'imap-mail.outlook.com',
      port: 993,
      protocol: 'imap_ssl'
    },
    sending: {
      name: 'Outlook Sending',
      host: 'smtp-mail.outlook.com',
      port: 587,
      protocol: 'smtp'
    }
  },
  yahoo: {
    address: [
      "@yahoo.com"
    ],
    sources: {
      name: 'Yahoo Source',
      host: 'imap.mail.yahoo.com',
      port: 993,
      protocol: 'imap_ssl'
    },
    sending: {
      name: 'Yahoo Sending',
      host: 'smtp.mail.yahoo.com',
      port: 587,
      protocol: 'smtp'
    }
  }
};