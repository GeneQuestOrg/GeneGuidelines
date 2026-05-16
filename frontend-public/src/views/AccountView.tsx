import { Button, useAccount } from "@gene-guidelines/ui";

export interface AccountViewProps {
  onNav: (path: string) => void;
  onSignIn: () => void;
}

export function AccountView({ onNav, onSignIn }: AccountViewProps) {
  const [account, setAccount] = useAccount();

  if (account == null) {
    return (
      <section className="page page--narrow">
        <h1 className="page__title">Your account</h1>
        <p className="page__lead">
          Sign in to save preferences, follow diseases, and (for clinicians) submit guideline
          updates.
        </p>
        <p className="page__actions">
          <Button variant="primary" onClick={onSignIn}>
            Sign in or register
          </Button>
        </p>
      </section>
    );
  }

  return (
    <section className="page page--narrow">
      <h1 className="page__title">Your account</h1>
      <dl className="account-dl">
        <dt>Name</dt>
        <dd>{account.name}</dd>
        <dt>Email</dt>
        <dd>{account.email}</dd>
        <dt>Role</dt>
        <dd>{account.role}</dd>
        {account.institution ? (
          <>
            <dt>Institution</dt>
            <dd>{account.institution}</dd>
          </>
        ) : null}
      </dl>
      <p className="page__actions">
        <Button
          variant="ghost"
          onClick={() => {
            setAccount(null);
            onNav("/");
          }}
        >
          Sign out
        </Button>
      </p>
    </section>
  );
}
