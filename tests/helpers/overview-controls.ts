import {expect,type Page} from '@playwright/test'

/** Drive the same shared field through the visible desktop or mobile surface. */
export async function selectOverviewFilter(page:Page,label:string,value:string){
  const control=page.getByLabel(label,{exact:true}).and(page.locator(':visible'))
  let opened:'mobile'|'more'|null=null
  if(!await control.count()){
    const more=page.getByRole('button',{name:'Weitere Filter',exact:true})
    if(await more.isVisible()){await more.click();opened='more'}
    else{await page.getByRole('button',{name:'Filter',exact:true}).click();opened='mobile'}
  }
  await expect(control).toBeVisible();await control.selectOption(value)
  if(opened==='mobile')await page.getByRole('button',{name:'Filter schließen',exact:true}).click()
  else if(opened==='more')await page.keyboard.press('Escape')
}
