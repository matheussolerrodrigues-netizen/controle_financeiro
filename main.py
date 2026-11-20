import sys, sqlite3, shutil
from pathlib import Path
from datetime import date, datetime
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

APP_DIR = Path.home() / "ControleFinanceiro"
APP_DIR.mkdir(exist_ok=True)
DB_PATH = APP_DIR / "financeiro.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, closing_day INTEGER NOT NULL,
 due_day INTEGER NOT NULL, credit_limit REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS entries(
 id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, description TEXT NOT NULL,
 amount REAL NOT NULL, category TEXT, payment TEXT, card_id INTEGER, installments INTEGER DEFAULT 1,
 first_month TEXT NOT NULL, recurring INTEGER DEFAULT 0, created_at TEXT,
 FOREIGN KEY(card_id) REFERENCES cards(id)
);
CREATE TABLE IF NOT EXISTS occurrences(
 id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL, month TEXT NOT NULL,
 amount REAL NOT NULL, installment_no INTEGER NOT NULL, paid INTEGER DEFAULT 0,
 FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
);
"""

def money(v):
    return ("R$ {:,.2f}".format(v)).replace(",", "X").replace(".", ",").replace("X", ".")

def month_add(ym, n):
    y,m=map(int,ym.split("-")); z=y*12+(m-1)+n
    return f"{z//12:04d}-{z%12+1:02d}"

def month_label(ym):
    y,m=map(int,ym.split("-"))
    return f"{['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'][m-1]} de {y}"

class FinanceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controle Financeiro Pessoal")
        self.resize(1180, 760)
        self.db=sqlite3.connect(DB_PATH)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.seed_cards()
        self.setStyleSheet("""
        QWidget { background:#f5f7fb; color:#17243a; font-family:'Segoe UI'; font-size:10pt; }
        QMainWindow { background:#f5f7fb; }
        QTabWidget::pane { border:1px solid #e2e8f0; background:white; border-radius:10px; }
        QTabBar::tab { background:#e9eef6; padding:12px 22px; margin-right:4px; border-top-left-radius:8px; border-top-right-radius:8px; }
        QTabBar::tab:selected { background:#ffffff; color:#1769aa; font-weight:bold; }
        QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateEdit { background:white; border:1px solid #d6deea; border-radius:6px; padding:8px; min-height:20px; }
        QPushButton { background:#1769aa; color:white; border:0; border-radius:7px; padding:9px 16px; font-weight:600; }
        QPushButton:hover { background:#0f548b; }
        QPushButton[secondary="true"] { background:#e8eef6; color:#23415f; }
        QTableWidget { background:white; border:1px solid #e2e8f0; gridline-color:#edf1f6; border-radius:8px; }
        QHeaderView::section { background:#edf2f8; padding:9px; border:0; font-weight:bold; }
        QLabel#heading { font-size:20pt; font-weight:700; color:#152b46; }
        QLabel#muted { color:#64748b; }
        """)
        root=QWidget(); lay=QVBoxLayout(root); lay.setContentsMargins(22,18,22,20)
        header=QHBoxLayout()
        title=QLabel("Controle Financeiro"); title.setObjectName("heading")
        subtitle=QLabel("  •  Organização simples das suas finanças"); subtitle.setObjectName("muted")
        header.addWidget(title); header.addWidget(subtitle); header.addStretch()
        lay.addLayout(header)
        self.tabs=QTabWidget()
        self.tabs.addTab(self.dashboard_tab(),"Visão geral")
        self.tabs.addTab(self.launch_tab(),"Lançamentos")
        self.tabs.addTab(self.month_tab(),"Meses / faturas")
        self.tabs.addTab(self.cards_tab(),"Cartões")
        self.tabs.addTab(self.settings_tab(),"Backup")
        lay.addWidget(self.tabs)
        self.setCentralWidget(root)
        self.refresh_all()

    def seed_cards(self):
        cur=self.db.execute("SELECT COUNT(*) FROM cards")
        if cur.fetchone()[0]==0:
            self.db.executemany("INSERT INTO cards(name,closing_day,due_day,credit_limit) VALUES(?,?,?,?)",
                [("Cartão 1",20,27,0),("Cartão 2",10,17,0),("Cartão 3",5,12,0)])
            self.db.commit()

    def label(self,text,muted=False):
        x=QLabel(text)
        if muted: x.setObjectName("muted")
        return x

    def dashboard_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        l.addWidget(self.label("Seu panorama financeiro",True))
        self.dash_cards=QHBoxLayout(); l.addLayout(self.dash_cards)
        self.dash_table=QTableWidget(0,4); self.dash_table.setHorizontalHeaderLabels(["Mês","Entradas previstas","Saídas previstas","Saldo previsto"])
        self.dash_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.dash_table)
        return w

    def metric(self, title):
        box=QFrame(); box.setStyleSheet("QFrame{background:white;border:1px solid #e3eaf2;border-radius:10px;padding:12px}")
        v=QVBoxLayout(box); a=QLabel(title); a.setObjectName("muted"); b=QLabel("R$ 0,00"); b.setStyleSheet("font-size:19pt;font-weight:700;color:#1769aa")
        v.addWidget(a); v.addWidget(b); return box,b

    def launch_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        form=QGroupBox("Novo lançamento"); g=QGridLayout(form)
        self.kind=QComboBox(); self.kind.addItems(["Despesa","Entrada"])
        self.desc=QLineEdit(); self.desc.setPlaceholderText("Ex.: mercado, salário, combustível...")
        self.amount=QDoubleSpinBox(); self.amount.setMaximum(99999999); self.amount.setDecimals(2); self.amount.setPrefix("R$ ")
        self.category=QComboBox(); self.category.addItems(["Moradia","Alimentação","Transporte","Saúde","Educação","Lazer","Compras","Assinaturas","Impostos","Salário","Renda extra","Ajuda de custo","Outros"])
        self.payment=QComboBox(); self.payment.addItems(["Pix","Dinheiro","Débito","Transferência","Cartão de crédito"])
        self.card=QComboBox()
        self.installments=QSpinBox(); self.installments.setRange(1,120); self.installments.setValue(1)
        self.first_month=QLineEdit(date.today().strftime("%Y-%m")); self.first_month.setPlaceholderText("AAAA-MM")
        self.recurring=QCheckBox("Repetir mensalmente (entrada)")
        fields=[("Tipo",self.kind),("Descrição",self.desc),("Valor total",self.amount),("Categoria",self.category),
                ("Forma de pagamento",self.payment),("Cartão",self.card),("Parcelas",self.installments),("1ª parcela / mês",self.first_month)]
        for i,(name,widget) in enumerate(fields):
            g.addWidget(QLabel(name),i//4*2,i%4); g.addWidget(widget,i//4*2+1,i%4)
        g.addWidget(self.recurring,4,0,1,2)
        btn=QPushButton("Adicionar lançamento"); btn.clicked.connect(self.add_entry); g.addWidget(btn,4,3)
        l.addWidget(form)
        self.entries_table=QTableWidget(0,7); self.entries_table.setHorizontalHeaderLabels(["Descrição","Tipo","Valor","Categoria","Pagamento","Parcelas","Primeiro mês"])
        self.entries_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); l.addWidget(self.entries_table)
        actions=QHBoxLayout()
        edit=QPushButton("Editar selecionado"); edit.clicked.connect(self.edit_entry)
        delete=QPushButton("Excluir selecionado"); delete.setProperty("secondary",True); delete.clicked.connect(self.delete_entry)
        actions.addWidget(edit); actions.addWidget(delete); actions.addStretch(); l.addLayout(actions)
        self.payment.currentTextChanged.connect(self.toggle_card)
        self.kind.currentTextChanged.connect(self.toggle_recurring)
        return w

    def toggle_card(self):
        self.card.setEnabled(self.payment.currentText()=="Cartão de crédito")
    def toggle_recurring(self):
        self.recurring.setEnabled(self.kind.currentText()=="Entrada")

    def add_entry(self):
        desc=self.desc.text().strip(); amount=self.amount.value(); fm=self.first_month.text().strip()
        try:
            y,m=map(int,fm.split("-")); assert 1<=m<=12 and y>=2000
        except: QMessageBox.warning(self,"Mês inválido","Informe o mês no formato AAAA-MM, por exemplo 2026-12."); return
        if not desc or amount<=0:
            QMessageBox.warning(self,"Dados incompletos","Informe uma descrição e um valor maior que zero."); return
        kind="Despesa" if self.kind.currentText()=="Despesa" else "Entrada"
        pay=self.payment.currentText()
        card_id=self.card.currentData() if pay=="Cartão de crédito" else None
        n=self.installments.value() if kind=="Despesa" and pay=="Cartão de crédito" else 1
        total=amount
        recurring=int(self.recurring.isChecked() and kind=="Entrada")
        cur=self.db.execute("""INSERT INTO entries(kind,description,amount,category,payment,card_id,installments,first_month,recurring,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(kind,desc,total,self.category.currentText(),pay,card_id,n,fm,recurring,datetime.now().isoformat()))
        eid=cur.lastrowid
        for i in range(n):
            self.db.execute("INSERT INTO occurrences(entry_id,month,amount,installment_no) VALUES(?,?,?,?)",(eid,month_add(fm,i),round(total/n,2),i+1))
        if recurring:
            for i in range(1,13):
                self.db.execute("INSERT INTO occurrences(entry_id,month,amount,installment_no) VALUES(?,?,?,?)",(eid,month_add(fm,i),total,i+1))
        self.db.commit()
        self.desc.clear(); self.amount.setValue(0); self.recurring.setChecked(False)
        self.refresh_all()

    def selected_entry(self):
        r=self.entries_table.currentRow()
        if r<0: return None
        return int(self.entries_table.item(r,0).data(Qt.UserRole))

    def edit_entry(self):
        eid=self.selected_entry()
        if not eid: return
        row=self.db.execute("SELECT description,amount,category,payment,installments,first_month FROM entries WHERE id=?",(eid,)).fetchone()
        if not row:return
        d=QDialog(self); d.setWindowTitle("Editar lançamento"); f=QFormLayout(d)
        desc=QLineEdit(row[0]); val=QDoubleSpinBox(); val.setMaximum(99999999); val.setDecimals(2); val.setValue(row[1])
        cat=QComboBox(); cat.addItems(["Moradia","Alimentação","Transporte","Saúde","Educação","Lazer","Compras","Assinaturas","Impostos","Salário","Renda extra","Ajuda de custo","Outros"]); cat.setCurrentText(row[2] or "Outros")
        pay=QComboBox(); pay.addItems(["Pix","Dinheiro","Débito","Transferência","Cartão de crédito"]); pay.setCurrentText(row[3])
        n=QSpinBox(); n.setRange(1,120); n.setValue(row[4])
        fm=QLineEdit(row[5])
        f.addRow("Descrição",desc); f.addRow("Valor total",val); f.addRow("Categoria",cat); f.addRow("Pagamento",pay); f.addRow("Parcelas",n); f.addRow("Primeiro mês",fm)
        ok=QPushButton("Salvar alterações"); ok.clicked.connect(d.accept); f.addRow(ok)
        if d.exec():
            try: y,m=map(int,fm.text().split("-")); assert 1<=m<=12
            except: QMessageBox.warning(self,"Mês inválido","Use AAAA-MM."); return
            self.db.execute("UPDATE entries SET description=?,amount=?,category=?,payment=?,installments=?,first_month=? WHERE id=?",
                (desc.text(),val.value(),cat.currentText(),pay.currentText(),n.value(),fm.text(),eid))
            self.db.execute("DELETE FROM occurrences WHERE entry_id=?",(eid,))
            for i in range(n.value()):
                self.db.execute("INSERT INTO occurrences(entry_id,month,amount,installment_no) VALUES(?,?,?,?)",(eid,month_add(fm.text(),i),round(val.value()/n.value(),2),i+1))
            self.db.commit(); self.refresh_all()

    def delete_entry(self):
        eid=self.selected_entry()
        if eid and QMessageBox.question(self,"Excluir","Excluir este lançamento e todas as parcelas?")==QMessageBox.Yes:
            self.db.execute("DELETE FROM occurrences WHERE entry_id=?",(eid,)); self.db.execute("DELETE FROM entries WHERE id=?",(eid,)); self.db.commit(); self.refresh_all()

    def month_tab(self):
        w=QWidget(); l=QVBoxLayout(w); top=QHBoxLayout()
        self.month_select=QComboBox(); self.month_select.currentTextChanged.connect(self.refresh_month)
        top.addWidget(QLabel("Consultar mês:")); top.addWidget(self.month_select); top.addStretch()
        l.addLayout(top)
        self.month_summary=QLabel(); self.month_summary.setStyleSheet("font-size:14pt;font-weight:700;padding:8px")
        l.addWidget(self.month_summary)
        self.month_table=QTableWidget(0,7); self.month_table.setHorizontalHeaderLabels(["Descrição","Categoria","Cartão / forma","Parcela","Valor","Status","Ação"])
        self.month_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); l.addWidget(self.month_table)
        return w

    def refresh_month(self):
        if not hasattr(self,"month_select") or not self.month_select.currentText(): return
        ym=self.month_select.currentData() or self.month_select.currentText()
        rows=self.db.execute("""SELECT o.id,e.description,e.category,e.payment,c.name,o.installment_no,e.installments,o.amount,o.paid
        FROM occurrences o JOIN entries e ON e.id=o.entry_id LEFT JOIN cards c ON c.id=e.card_id
        WHERE o.month=? ORDER BY e.description""",(ym,)).fetchall()
        self.month_table.setRowCount(len(rows)); inc=out=0
        for r,row in enumerate(rows):
            oid,desc,cat,pay,card,no,n,amt,paid=row
            kind=self.db.execute("SELECT kind FROM entries e JOIN occurrences o ON o.entry_id=e.id WHERE o.id=?",(oid,)).fetchone()[0]
            if kind=="Entrada": inc+=amt
            else: out+=amt
            vals=[desc,cat or "",card or pay,f"{no}/{n}",money(amt),"Pago" if paid else "Pendente"]
            for c,v in enumerate(vals): self.month_table.setItem(r,c,QTableWidgetItem(str(v)))
            b=QPushButton("Marcar pago" if not paid else "Desmarcar")
            b.clicked.connect(lambda _,x=oid:self.toggle_paid(x)); self.month_table.setCellWidget(r,6,b)
        self.month_summary.setText(f"Entradas: {money(inc)}     •     Saídas: {money(out)}     •     Saldo: {money(inc-out)}")

    def toggle_paid(self,oid):
        self.db.execute("UPDATE occurrences SET paid=1-paid WHERE id=?",(oid,)); self.db.commit(); self.refresh_all()

    def cards_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        l.addWidget(self.label("Configure o nome, fechamento e vencimento de cada cartão.",True))
        self.card_table=QTableWidget(0,5); self.card_table.setHorizontalHeaderLabels(["Cartão","Fechamento (dia)","Vencimento (dia)","Limite (R$)","ID"])
        self.card_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); l.addWidget(self.card_table)
        btn=QPushButton("Salvar cartões"); btn.clicked.connect(self.save_cards); l.addWidget(btn)
        return w

    def save_cards(self):
        for r in range(self.card_table.rowCount()):
            try:
                cid=int(self.card_table.item(r,4).text()); name=self.card_table.item(r,0).text()
                close=int(self.card_table.item(r,1).text()); due=int(self.card_table.item(r,2).text()); lim=float(self.card_table.item(r,3).text().replace(",","." ))
                if not (1<=close<=31 and 1<=due<=31): raise ValueError()
                self.db.execute("UPDATE cards SET name=?,closing_day=?,due_day=?,credit_limit=? WHERE id=?",(name,close,due,lim,cid))
            except: QMessageBox.warning(self,"Verifique os dados","Use dias de 1 a 31 e limite numérico."); return
        self.db.commit(); self.refresh_all(); QMessageBox.information(self,"Salvo","Cartões atualizados.")

    def settings_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        l.addWidget(QLabel("Backup do banco de dados"))
        l.addWidget(self.label(f"Os dados ficam salvos localmente em: {DB_PATH}",True))
        b=QPushButton("Criar backup..."); b.clicked.connect(self.backup); l.addWidget(b); l.addStretch()
        return w

    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,"Salvar backup","financeiro-backup.db","Banco SQLite (*.db)")
        if path:
            self.db.commit(); shutil.copy2(DB_PATH,path); QMessageBox.information(self,"Backup criado","Backup salvo com sucesso.")

    def refresh_all(self):
        cards=self.db.execute("SELECT id,name FROM cards ORDER BY id").fetchall()
        if hasattr(self,"card"):
            self.card.clear()
            for cid,name in cards:self.card.addItem(name,cid)
            self.card.setEnabled(self.payment.currentText()=="Cartão de crédito")
        if hasattr(self,"entries_table"):
            rows=self.db.execute("SELECT id,description,kind,amount,category,payment,installments,first_month FROM entries ORDER BY id DESC").fetchall()
            self.entries_table.setRowCount(len(rows))
            for r,row in enumerate(rows):
                vals=row[1:]
                for c,v in enumerate(vals):
                    item=QTableWidgetItem(money(v) if c==2 else str(v)); 
                    if c==0:item.setData(Qt.UserRole,row[0])
                    self.entries_table.setItem(r,c,item)
        if hasattr(self,"card_table"):
            self.card_table.setRowCount(len(cards))
            data=self.db.execute("SELECT id,name,closing_day,due_day,credit_limit FROM cards ORDER BY id").fetchall()
            for r,row in enumerate(data):
                for c,v in enumerate([row[1],row[2],row[3],row[4],row[0]]):self.card_table.setItem(r,c,QTableWidgetItem(str(v)))
        if hasattr(self,"month_select"):
            current=self.month_select.currentData() or date.today().strftime("%Y-%m")
            months=[x[0] for x in self.db.execute("SELECT DISTINCT month FROM occurrences ORDER BY month").fetchall()]
            if current not in months: months.append(current)
            months=sorted(set(months))
            self.month_select.blockSignals(True); self.month_select.clear()
            for m in months:self.month_select.addItem(month_label(m),m)
            idx=self.month_select.findData(current)
            self.month_select.setCurrentIndex(max(0,idx)); self.month_select.blockSignals(False)
            self.refresh_month()
        if hasattr(self,"dash_cards"):
            while self.dash_cards.count():
                it=self.dash_cards.takeAt(0)
                if it.widget():it.widget().deleteLater()
            today=date.today().strftime("%Y-%m")
            inc=self.db.execute("SELECT COALESCE(SUM(o.amount),0) FROM occurrences o JOIN entries e ON e.id=o.entry_id WHERE o.month=? AND e.kind='Entrada'",(today,)).fetchone()[0]
            out=self.db.execute("SELECT COALESCE(SUM(o.amount),0) FROM occurrences o JOIN entries e ON e.id=o.entry_id WHERE o.month=? AND e.kind='Despesa'",(today,)).fetchone()[0]
            for t,v in [("Entradas do mês",inc),("Despesas do mês",out),("Saldo previsto",inc-out)]:
                box,val=self.metric(t); val.setText(money(v)); self.dash_cards.addWidget(box)
            months=sorted(set(x[0] for x in self.db.execute("SELECT DISTINCT month FROM occurrences").fetchall())|{today})
            self.dash_table.setRowCount(len(months))
            for r,m in enumerate(months):
                a=self.db.execute("SELECT COALESCE(SUM(o.amount),0) FROM occurrences o JOIN entries e ON e.id=o.entry_id WHERE o.month=? AND e.kind='Entrada'",(m,)).fetchone()[0]
                b=self.db.execute("SELECT COALESCE(SUM(o.amount),0) FROM occurrences o JOIN entries e ON e.id=o.entry_id WHERE o.month=? AND e.kind='Despesa'",(m,)).fetchone()[0]
                for c,v in enumerate([month_label(m),money(a),money(b),money(a-b)]):self.dash_table.setItem(r,c,QTableWidgetItem(v))

if __name__=="__main__":
    app=QApplication(sys.argv)
    win=FinanceApp(); win.show()
    sys.exit(app.exec())
