class TextEditor:

    def __init__(self):
        self.x = ''
        self.position = 0

    def addText(self, text: str) -> None:
        if len(self.x) != 0:
            self.x = self.x[:self.position] + text + self.x[self.position+1:]
            self.position = len(self.x)
        else:
            self.x = text
            self.position = len(self.x)

        print('a', self.x, self.position)

    def deleteText(self, k: int) -> int:
        a = k
        while a:
            if len(self.x) > 0:
                if len(self.x) == self.position:
                    self.x = self.x[:self.position-1]
                else:
                    self.x = self.x[:self.position] + self.x[:self.position+1]
                self.position -= 1
                # print(self.x, self.position)
                a -= 1
            else:
                print(a)
                return k-a
        print('b', self.x, self.position)
        return k-a

    def cursorLeft(self, k: int) -> str:
        a = k
        while a:
            if self.position > 0:
                self.position -= 1
                a -= 1
            else:
                return ''
        print('c', self.x, self.position)

        if self.position > 0:
            if self.position >= 10:
                return self.x[self.position-10:self.position]
            else:
                return self.x[:self.position]


    def cursorRight(self, k: int) -> str:
        a = k
        while a:
            if self.position != len(self.x):
                self.position += 1
                a -= 1
            else:
                return self.x[self.position-10:self.position]

        if self.position < len(self.x):
            if self.position >= 10:
                return self.x[self.position-10:self.position]
            else:
                return self.x[:self.position]

# ["TextEditor","addText","deleteText","addText","cursorRight","cursorLeft","deleteText","cursorLeft","cursorRight"]
obj = TextEditor()
obj.addText("leetcode")
obj.deleteText(4)
obj.addText("practice")
print(obj.cursorRight(3))
print(obj.cursorLeft(8))
obj.addText('')
obj.deleteText(10)
print(obj.cursorLeft(2))
print(obj.cursorRight(6))
#[null,null,4,null,"etpractice","leet",4,"","practi"]
