from orator.migrations import Migration


class CreateTransactionsTable(Migration):

    def up(self):
        with self.schema.create('transactions') as table:
            table.increments('id')
            table.integer('user_id').unsigned()
            table.string('transaction_code').unique()
            table.decimal('amount', 10, 2)
            table.string('bank')

            table.timestamps()

    def down(self):
        self.schema.drop('transactions')
